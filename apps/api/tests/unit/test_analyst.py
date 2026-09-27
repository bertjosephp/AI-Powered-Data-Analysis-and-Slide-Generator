import json
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.schemas.deck import ResolvedChartInsightSlide, ResolvedKpiSlide
from app.schemas.insights import DeckPlan, Insights, Report
from app.schemas.options import AnalysisOptions
from app.services.analysis.battery import BatteryResult, run_battery
from app.services.deck.resolve import resolve_slides
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.analyst import MAX_TOOL_CALLS, ClaudeAnalyst
from app.services.llm.context import AnalysisContext
from app.services.llm.mock import MockAnalyst
from app.services.llm.tools import TOOLS, ToolRunner

FIXTURES = Path(__file__).parent.parent / "fixtures"
DATA = Path(__file__).parents[2] / "app" / "sample_data"


@cache
def _battery() -> BatteryResult:
    df = load_dataset((DATA / "saas_churn.csv").read_bytes(), "saas_churn.csv", 10**8)
    return run_battery(df, build_profile(df, 200_000))


def _context(with_frame: bool = True, **options: Any) -> AnalysisContext:
    b = _battery()
    df = load_dataset((DATA / "saas_churn.csv").read_bytes(), "saas_churn.csv", 10**8)
    return AnalysisContext(
        profile=build_profile(df, 200_000),
        findings=[f.model_copy(deep=True) for f in b.findings],
        roles=b.roles,
        options=AnalysisOptions(num_slides=8, **options),
        dataset_name="saas_churn.csv",
        frame=b.frame if with_frame else None,
    )


@pytest.fixture(scope="module")
def good_insights() -> Insights:
    return Insights.model_validate_json((FIXTURES / "llm_response.json").read_text())


# ---------- fake Anthropic client ----------


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use(i: int, name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"tu{i}", name=name, input=args)


def _turn(*blocks: SimpleNamespace, stop: str | None = None) -> SimpleNamespace:
    uses = any(b.type == "tool_use" for b in blocks)
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop or ("tool_use" if uses else "end_turn")
    )


def _report(parsed: Any, stop: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop, content=[])


class FakeMessages:
    """`reports` are outcomes for the structured calls. An Insights outcome serves both:
    the report call gets its Report part, and the next slides call gets its slides."""

    def __init__(self, turns: list[Any], reports: list[Any]) -> None:
        self.turns, self.reports = turns, reports
        self.create_calls: list[dict[str, Any]] = []
        self.parse_calls: list[dict[str, Any]] = []
        self._slides: list[Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.create_calls.append({**kwargs, "messages": list(kwargs["messages"])})
        outcome = self.turns.pop(0) if self.turns else _turn(_text("Done exploring."))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def parse(self, **kwargs: Any) -> Any:
        self.parse_calls.append({**kwargs, "messages": list(kwargs["messages"])})
        fmt = kwargs["output_format"]
        if fmt is DeckPlan and self._slides is not None:
            slides, self._slides = self._slides, None
            return _report(DeckPlan(slides=slides))
        outcome = self.reports.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        insights = outcome.parsed_output
        if not isinstance(insights, Insights):
            return outcome
        if fmt is Report:
            self._slides = insights.slides
            report = Report(**{k: getattr(insights, k) for k in Report.model_fields})
            return _report(report, outcome.stop_reason)
        return _report(DeckPlan(slides=insights.slides), outcome.stop_reason)


def _client(turns: list[Any], reports: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(messages=FakeMessages(turns, reports))


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=req), body=None)


def _validation_error() -> ValidationError:
    try:
        Insights.model_validate_json("{}")
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


# ---------- the loop ----------


async def test_explores_then_writes_a_structured_report(good_insights: Insights) -> None:
    ctx = _context(question="Why do customers churn?")
    client = _client([_turn(_text("I have what I need."))], [_report(good_insights)])
    out = await ClaudeAnalyst(client, "claude-sonnet-5").generate(ctx)

    assert out.insights == good_insights and out.follow_ups == [] and out.tool_calls == 0
    create = client.messages.create_calls[0]
    assert create["tool_choice"] == {"type": "auto"} and {t["name"] for t in create["tools"]} >= {
        "compare_segments",
        "metric_by_bins",
        "trend",
    }
    prompt_block = create["messages"][0]["content"][0]
    assert prompt_block["cache_control"] == {"type": "ephemeral"}
    assert create["system"][0]["cache_control"] == {"type": "ephemeral"}
    prompt = prompt_block["text"]
    assert "User's question: Why do customers churn?" in prompt
    assert '"id":"F1"' in prompt and "<dataset_profile>" in prompt
    assert "ACC-00001" not in prompt  # no raw rows

    report, slides = client.messages.parse_calls
    assert report["output_format"] is Report and slides["output_format"] is DeckPlan
    assert report["tool_choice"] == slides["tool_choice"] == {"type": "none"}
    assert report["messages"][-1]["role"] == "user"
    assert "final report" in str(report["messages"][-1]["content"])
    # The slides call continues the same conversation, with the report as Claude's turn.
    assert slides["messages"][: len(report["messages"])] == report["messages"]
    written = slides["messages"][-2]
    assert written["role"] == "assistant"
    assert Report.model_validate_json(written["content"][0]["text"]) == Report(
        **{k: getattr(good_insights, k) for k in Report.model_fields}
    )
    assert "slides" in str(slides["messages"][-1]["content"])


async def test_tool_calls_run_on_the_dataset_and_become_findings(good_insights: Insights) -> None:
    ctx = _context()
    n = len(ctx.findings)
    client = _client(
        [
            _turn(
                _text("Checking churn by plan among monthly payers."),
                _tool_use(
                    1,
                    "compare_segments",
                    {
                        "metric": "churned",
                        "dimension": "plan",
                        "where": {"column": "billing_cycle", "value": "Monthly"},
                    },
                ),
            ),
            _turn(_text("Enough.")),
        ],
        [_report(good_insights)],
    )
    out = await ClaudeAnalyst(client, "m").generate(ctx)

    assert out.tool_calls == 1
    (follow_up,) = out.follow_ups
    assert follow_up.id == f"F{n + 1}" and follow_up.source == "follow_up"
    assert follow_up.filter == "billing_cycle = Monthly"
    # The tool result went back to Claude as the finding's JSON.
    second = client.messages.create_calls[1]["messages"]
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu1"
    assert json.loads(result["content"])["id"] == follow_up.id and result["is_error"] is False


async def test_bad_tool_arguments_come_back_as_errors(good_insights: Insights) -> None:
    client = _client(
        [
            _turn(
                _tool_use(
                    1, "compare_segments", {"metric": "nope", "dimension": "plan", "where": None}
                )
            ),
            _turn(_text("OK.")),
        ],
        [_report(good_insights)],
    )
    out = await ClaudeAnalyst(client, "m").generate(_context())
    result = client.messages.create_calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Unknown metric" in result["content"]
    assert out.follow_ups == []


def test_tools_are_not_strict() -> None:
    # Strict tools plus the Insights output schema exceed the API's compiled-grammar
    # limit ("The compiled grammar is too large"), failing every real report call.
    assert not any(t.get("strict") for t in TOOLS)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("compare_segments", {"metric": "churned"}),  # missing dimension
        ("compare_segments", {"metric": "churned", "dimension": "plan", "where": "plan=Pro"}),
        ("metric_by_bins", {"metric": "churned", "driver": "tenure_months", "bins": "four"}),
        ("crosstab", {"dimension_a": "plan", "dimension_b": None}),
        ("no_such_tool", {}),
    ],
)
def test_malformed_tool_arguments_become_error_results(name: str, args: dict[str, Any]) -> None:
    b = _battery()
    runner = ToolRunner(b.frame, b.roles, first_id=100)
    content, is_error = runner.run(name, args)
    assert is_error and content and runner.findings == []


async def test_tool_budget_is_enforced(good_insights: Insights) -> None:
    def many(start: int) -> SimpleNamespace:
        return _turn(
            *(
                _tool_use(
                    start + i,
                    "metric_by_bins",
                    {"metric": "churned", "driver": "seats", "bins": 4, "where": None},
                )
                for i in range(3)
            )
        )

    client = _client([many(0), many(3), many(6), many(9)], [_report(good_insights)])
    out = await ClaudeAnalyst(client, "m").generate(_context())

    assert out.tool_calls == MAX_TOOL_CALLS
    assert len(client.messages.create_calls) == 3  # stopped as soon as the budget ran out
    last_results = client.messages.parse_calls[0]["messages"][-1]["content"]
    over = [r for r in last_results if r.get("type") == "tool_result" and r["is_error"]]
    assert len(over) == 1 and "budget" in over[0]["content"]  # 9th call refused, still answered
    assert last_results[-1]["type"] == "text"  # final instruction appended to the same turn


async def test_without_the_dataset_there_are_no_tools(good_insights: Insights) -> None:
    client = _client([], [_report(good_insights)])
    out = await ClaudeAnalyst(client, "m").generate(_context(with_frame=False))
    assert out.insights == good_insights
    assert client.messages.create_calls == []
    assert all("tools" not in call for call in client.messages.parse_calls)
    assert (
        "Follow-up tools: unavailable"
        in client.messages.parse_calls[0]["messages"][0]["content"][0]["text"]
    )


async def test_report_is_retried_once_on_invalid_output(good_insights: Insights) -> None:
    client = _client([], [_validation_error(), _report(good_insights)])
    out = await ClaudeAnalyst(client, "m").generate(_context(with_frame=False))
    assert out.insights == good_insights and len(client.messages.parse_calls) == 3


async def test_slides_are_retried_when_the_deck_is_empty(good_insights: Insights) -> None:
    empty = good_insights.model_copy(update={"slides": []})
    client = _client([], [_report(empty), _report(good_insights)])
    out = await ClaudeAnalyst(client, "m").generate(_context(with_frame=False))
    assert out.insights == good_insights  # report from the first, slides from the retry
    assert [c["output_format"] for c in client.messages.parse_calls] == [Report, DeckPlan, DeckPlan]


async def test_gives_up_with_schema_error(good_insights: Insights) -> None:
    empty = good_insights.model_copy(update={"slides": []})
    client = _client([], [_report(None, "max_tokens"), _report(empty), _report(empty)])
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(client, "m").generate(_context(with_frame=False))
    assert exc.value.code == ErrorCode.LLM_SCHEMA_ERROR and "slides" in exc.value.message


async def test_refusal_during_exploration_stops() -> None:
    client = _client([_turn(_text(""), stop="refusal")], [])
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(client, "m").generate(_context())
    assert exc.value.code == ErrorCode.LLM_ERROR and "declined" in exc.value.message


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (_status_error(anthropic.AuthenticationError, 401), "key was rejected"),
        (_status_error(anthropic.RateLimitError, 429), "rate limit"),
        (_status_error(anthropic.InternalServerError, 500), "API error 500"),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")),
            "Could not reach",
        ),
    ],
)
async def test_api_errors_map_to_llm_error(error: Exception, fragment: str) -> None:
    client = _client([error], [])
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(client, "m").generate(_context())
    assert exc.value.code == ErrorCode.LLM_ERROR and fragment in exc.value.message


# ---------- mock analyst ----------


async def test_mock_analyst_builds_a_deck_from_findings() -> None:
    ctx = _context(question="Why do customers churn?")
    out = await MockAnalyst(latency_s=0).generate(ctx)
    insights = out.insights
    assert insights == (await MockAnalyst(latency_s=0).generate(ctx)).insights  # deterministic
    assert insights.questions_answered[0].question == "Why do customers churn?"
    first_story = next(f for f in ctx.findings if f.kind != "drivers")
    assert insights.key_findings[0].finding_ids == [first_story.id]

    layouts = [s.layout for s in insights.slides]
    assert len(layouts) == 8 and layouts[0] == "title" and layouts[-1] == "next_steps"
    resolved = resolve_slides(insights.slides, ctx.profile, "saas_churn.csv", findings=ctx.findings)
    kpis = next(s for s in resolved if isinstance(s, ResolvedKpiSlide))
    charts = [s for s in resolved if isinstance(s, ResolvedChartInsightSlide)]
    assert len(kpis.kpis) == 4 and all(c.chart is not None for c in charts)
