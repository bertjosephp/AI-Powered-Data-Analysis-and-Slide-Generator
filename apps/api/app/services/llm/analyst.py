"""Findings -> Insights, with Claude digging deeper through follow-up tools.

Two phases over one conversation:
  1. Explore: Claude reads the ranked findings and may call analysis tools
     (at most MAX_TOOL_CALLS, over at most MAX_ROUNDS turns).
  2. Report: two structured-output calls (tool_choice "none"): the written report,
     then the slides. One schema covering both exceeds the API's grammar limit.
  3. Shorten: if any slide text is longer than its box, one small call rewrites
     just those strings.
The full assistant content (including thinking blocks) is appended every turn,
and the static system prompt and the large first message carry cache breakpoints.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.errors import AppError, ErrorCode
from app.schemas.insights import DeckPlan, Insights, Report
from app.services.llm.context import AnalysisContext, AnalystOutput
from app.services.llm.prompts import (
    FINAL_INSTRUCTION,
    SLIDES_INSTRUCTION,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.llm.shorten import (
    SHORTEN_SYSTEM,
    Rewrites,
    apply_rewrites,
    find_overlong,
    shorten_prompt,
)
from app.services.llm.tools import TOOLS, ToolRunner
from app.services.llm.usage import Usage

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

MAX_OUTPUT_TOKENS = 16_000
EXPLORE_MAX_TOKENS = 8_000
MAX_TOOL_CALLS = 8
MAX_ROUNDS = 4
REPORT_ATTEMPTS = 2
SHORTEN_MAX_TOKENS = 2_000
BUDGET_EXHAUSTED = "Tool budget exhausted. Write the final report from the findings you have."


class ClaudeAnalyst:
    def __init__(self, client: Any, model: str) -> None:
        # `client` is an AsyncAnthropic; typed loosely so tests can pass a fake.
        self._client = client
        self._model = model
        self._usage = Usage()

    async def generate(self, context: AnalysisContext) -> AnalystOutput:
        self._usage = Usage()
        system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": build_user_prompt(context),
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ]
        runner = (
            ToolRunner(context.frame, context.roles, first_id=len(context.findings) + 1)
            if context.frame is not None
            else None
        )
        calls = await self._explore(system, messages, runner) if runner else 0
        insights = await self._report(system, messages, tools_enabled=runner is not None)
        return AnalystOutput(
            insights=insights,
            follow_ups=runner.findings if runner else [],
            tool_calls=calls,
            usage=self._usage,
        )

    async def _explore(
        self, system: list[dict[str, Any]], messages: list[dict[str, Any]], runner: ToolRunner
    ) -> int:
        calls = 0
        for _ in range(MAX_ROUNDS):
            response = await self._call(
                self._client.messages.create,
                model=self._model,
                max_tokens=EXPLORE_MAX_TOKENS,
                system=system,
                tools=TOOLS,
                tool_choice={"type": "auto"},
                messages=messages,
            )
            self._check_refusal(response)
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                break
            results: list[dict[str, Any]] = []
            for use in tool_uses:  # every tool_use needs a result, even over budget
                if calls >= MAX_TOOL_CALLS:
                    content, is_error = BUDGET_EXHAUSTED, True
                else:
                    calls += 1
                    content, is_error = await run_in_threadpool(runner.run, use.name, use.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
            if calls >= MAX_TOOL_CALLS:
                break
        log.info("Analyst made %d follow-up calls", calls)
        return calls

    async def _report(
        self, system: list[dict[str, Any]], messages: list[dict[str, Any]], *, tools_enabled: bool
    ) -> Insights:
        conversation = [*messages]
        if conversation[-1]["role"] == "user":
            # Last turn was tool results: add the instruction to that same user turn.
            conversation[-1] = {
                "role": "user",
                "content": [
                    *conversation[-1]["content"],
                    {"type": "text", "text": FINAL_INSTRUCTION},
                ],
            }
        else:
            conversation.append({"role": "user", "content": FINAL_INSTRUCTION})
        # Earlier tool_use blocks require the tools to be declared; "none" forbids new calls.
        tool_args: dict[str, Any] = (
            {"tools": TOOLS, "tool_choice": {"type": "none"}} if tools_enabled else {}
        )

        report = await self._structured("report", system, conversation, Report, tool_args)
        conversation += [
            {"role": "assistant", "content": [{"type": "text", "text": report.model_dump_json()}]},
            {"role": "user", "content": SLIDES_INSTRUCTION},
        ]
        deck = await self._structured(
            "slides",
            system,
            conversation,
            DeckPlan,
            tool_args,
            problem=lambda d: None if d.slides else "the deck had no slides",
        )
        deck = await self._shorten(deck)
        return Insights(**dict(report), slides=deck.slides)

    async def _shorten(self, deck: DeckPlan) -> DeckPlan:
        """Asks Claude to rewrite slide text that is longer than its box. Best effort:
        on any failure the deck is kept, and the fit step clips what is still too long."""
        overlong = find_overlong(deck)
        if not overlong:
            return deck
        try:
            response = await self._call(
                self._client.messages.parse,
                model=self._model,
                max_tokens=SHORTEN_MAX_TOKENS,
                system=SHORTEN_SYSTEM,
                messages=[{"role": "user", "content": shorten_prompt(overlong)}],
                output_format=Rewrites,
            )
        except (AppError, ValidationError) as e:
            log.warning("Shortening skipped: %s", e)
            return deck
        rewrites: Rewrites | None = response.parsed_output
        if rewrites is None:
            return deck
        log.info("Shortened %d overlong slide texts", len(overlong))
        return apply_rewrites(deck, overlong, rewrites)

    async def _structured(
        self,
        what: str,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        output: type[T],
        tool_args: dict[str, Any],
        problem: Callable[[T], str | None] = lambda _: None,
    ) -> T:
        """One structured-output call, retried once if the output is missing or unusable."""
        last_problem = "no attempts made"
        for attempt in range(1, REPORT_ATTEMPTS + 1):
            try:
                response = await self._call(
                    self._client.messages.parse,
                    model=self._model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=system,
                    messages=messages,
                    output_format=output,
                    **tool_args,
                )
            except ValidationError as e:
                last_problem = f"response failed schema validation: {e.error_count()} errors"
                log.warning("%s attempt %d: %s", what, attempt, last_problem)
                continue
            self._check_refusal(response)
            parsed: T | None = response.parsed_output
            if parsed is None:
                last_problem = f"no structured output (stop_reason={response.stop_reason})"
            elif (issue := problem(parsed)) is not None:
                last_problem = issue
            else:
                return parsed
            log.warning("%s attempt %d: %s", what, attempt, last_problem)
        raise AppError(
            ErrorCode.LLM_SCHEMA_ERROR,
            f"Could not get valid {what} after {REPORT_ATTEMPTS} attempts: {last_problem}.",
        )

    @staticmethod
    def _check_refusal(response: Any) -> None:
        if response.stop_reason == "refusal":
            raise AppError(ErrorCode.LLM_ERROR, "The model declined to analyze this dataset.")

    async def _call(self, method: Any, **kwargs: Any) -> Any:
        try:
            response = await method(**kwargs)
            self._usage.add(getattr(response, "usage", None))
            return response
        except anthropic.AuthenticationError as e:
            raise AppError(ErrorCode.LLM_ERROR, "The Anthropic API key was rejected.") from e
        except anthropic.RateLimitError as e:
            raise AppError(ErrorCode.LLM_ERROR, "Anthropic rate limit reached. Retry later.") from e
        except anthropic.APIStatusError as e:
            raise AppError(
                ErrorCode.LLM_ERROR, f"Anthropic API error {e.status_code}: {e.message}"
            ) from e
        except anthropic.APIConnectionError as e:
            raise AppError(ErrorCode.LLM_ERROR, "Could not reach the Anthropic API.") from e
