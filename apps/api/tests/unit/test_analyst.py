from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from pydantic import ValidationError

from app.errors import AppError, ErrorCode
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.analyst import ClaudeAnalyst
from app.services.llm.mock import MockAnalyst

FIXTURES = Path(__file__).parent.parent / "fixtures"
OPTIONS = AnalysisOptions(num_slides=6)


@pytest.fixture(scope="module")
def profile():  # type: ignore[no-untyped-def]
    df = load_dataset((FIXTURES / "sample.csv").read_bytes(), "sample.csv", 10**8)
    return build_profile(df, 200_000)


@pytest.fixture(scope="module")
def good_insights() -> Insights:
    return Insights.model_validate_json((FIXTURES / "llm_response.json").read_text())


class FakeMessages:
    """Mimics AsyncAnthropic().messages: returns or raises queued outcomes in order."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(*outcomes: Any) -> SimpleNamespace:
    return SimpleNamespace(messages=FakeMessages(list(outcomes)))


def _ok(insights: Insights | None, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(parsed_output=insights, stop_reason=stop_reason)


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=req), body=None)


def _validation_error() -> ValidationError:
    try:
        Insights.model_validate_json("{}")
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


async def test_returns_parsed_insights_and_sends_profile_not_rows(profile, good_insights) -> None:  # type: ignore[no-untyped-def]
    client = _client(_ok(good_insights))
    result = await ClaudeAnalyst(client, "claude-sonnet-5").generate(profile, OPTIONS, "sample.csv")

    assert result == good_insights
    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["output_format"] is Insights
    content = call["messages"][0]["content"]
    assert "<dataset_profile>" in content and "Number of slides: 6" in content
    assert "ORD-1000" not in content  # id column: no raw values leak into the prompt


async def test_retries_once_on_invalid_output_then_succeeds(profile, good_insights) -> None:  # type: ignore[no-untyped-def]
    client = _client(_validation_error(), _ok(good_insights))
    result = await ClaudeAnalyst(client, "m").generate(profile, OPTIONS, "x.csv")
    assert result == good_insights
    assert len(client.messages.calls) == 2


async def test_gives_up_with_schema_error(profile, good_insights) -> None:  # type: ignore[no-untyped-def]
    no_slides = good_insights.model_copy(update={"slides": []})
    client = _client(_ok(None, "max_tokens"), _ok(no_slides))
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(client, "m").generate(profile, OPTIONS, "x.csv")
    assert exc.value.code == ErrorCode.LLM_SCHEMA_ERROR


async def test_refusal_is_not_retried(profile) -> None:  # type: ignore[no-untyped-def]
    client = _client(_ok(None, "refusal"))
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(client, "m").generate(profile, OPTIONS, "x.csv")
    assert exc.value.code == ErrorCode.LLM_ERROR
    assert len(client.messages.calls) == 1


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (_status_error(anthropic.AuthenticationError, 401), "key was rejected"),
        (_status_error(anthropic.RateLimitError, 429), "rate limit"),
        (_status_error(anthropic.InternalServerError, 500), "API error 500"),
        (
            anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "Could not reach",
        ),
    ],
)
async def test_api_errors_map_to_llm_error(profile, error, fragment) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AppError) as exc:
        await ClaudeAnalyst(_client(error), "m").generate(profile, OPTIONS, "x.csv")
    assert exc.value.code == ErrorCode.LLM_ERROR
    assert fragment in exc.value.message


async def test_mock_analyst_is_deterministic_and_respects_slide_count(profile) -> None:  # type: ignore[no-untyped-def]
    mock = MockAnalyst(latency_s=0)
    a = await mock.generate(profile, OPTIONS, "sample.csv")
    b = await mock.generate(profile, OPTIONS, "sample.csv")
    assert a == b
    layouts = [s.layout for s in a.slides]
    assert len(layouts) == 6
    assert layouts[:3] == ["title", "executive_summary", "kpi_cards"]
    assert layouts[-1] == "next_steps"
    assert any("unit_price" in f.title for f in a.key_findings)


async def test_mock_analyst_slides_resolve_against_the_profile(profile) -> None:  # type: ignore[no-untyped-def]
    from app.schemas.deck import ResolvedChartInsightSlide, ResolvedKpiSlide
    from app.services.deck.resolve import resolve_slides

    insights = await MockAnalyst(latency_s=0).generate(
        profile, AnalysisOptions(num_slides=12), "sample.csv"
    )
    resolved = resolve_slides(insights.slides, profile, "sample.csv")
    kpis = [s for s in resolved if isinstance(s, ResolvedKpiSlide)]
    charts = [s for s in resolved if isinstance(s, ResolvedChartInsightSlide)]
    assert kpis and len(kpis[0].kpis) == 4  # every mock reference resolves
    assert len(charts) == 4 and all(c.chart is not None for c in charts)
