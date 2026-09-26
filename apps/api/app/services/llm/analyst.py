"""DatasetProfile -> Insights, via Claude structured outputs."""

import logging
from typing import Any, Protocol

import anthropic
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile
from app.services.llm.prompts import SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 16_000


class InsightsGenerator(Protocol):
    async def generate(
        self, profile: DatasetProfile, options: AnalysisOptions, dataset_name: str
    ) -> Insights: ...


class ClaudeAnalyst:
    def __init__(self, client: Any, model: str, max_attempts: int = 2) -> None:
        # `client` is an AsyncAnthropic; typed loosely so tests can pass a fake.
        self._client = client
        self._model = model
        self._max_attempts = max_attempts

    async def generate(
        self, profile: DatasetProfile, options: AnalysisOptions, dataset_name: str
    ) -> Insights:
        prompt = build_user_prompt(profile, options, dataset_name)
        last_problem = "no attempts made"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.messages.parse(
                    model=self._model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=Insights,
                )
            except ValidationError as e:
                last_problem = f"response failed schema validation: {e.error_count()} errors"
                log.warning("Insights attempt %d: %s", attempt, last_problem)
                continue
            except anthropic.AuthenticationError as e:
                raise AppError(ErrorCode.LLM_ERROR, "The Anthropic API key was rejected.") from e
            except anthropic.RateLimitError as e:
                raise AppError(
                    ErrorCode.LLM_ERROR, "Anthropic rate limit reached. Retry later."
                ) from e
            except anthropic.APIStatusError as e:
                raise AppError(
                    ErrorCode.LLM_ERROR, f"Anthropic API error {e.status_code}: {e.message}"
                ) from e
            except anthropic.APIConnectionError as e:
                raise AppError(ErrorCode.LLM_ERROR, "Could not reach the Anthropic API.") from e

            if response.stop_reason == "refusal":
                raise AppError(ErrorCode.LLM_ERROR, "The model declined to analyze this dataset.")
            insights: Insights | None = response.parsed_output
            if insights is None:
                last_problem = f"no structured output (stop_reason={response.stop_reason})"
            elif not insights.slide_outline:
                last_problem = "the slide outline was empty"
            else:
                return insights
            log.warning("Insights attempt %d: %s", attempt, last_problem)

        raise AppError(
            ErrorCode.LLM_SCHEMA_ERROR,
            f"Could not get valid insights after {self._max_attempts} attempts: {last_problem}.",
        )
