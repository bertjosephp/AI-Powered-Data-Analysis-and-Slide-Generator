"""The public-demo path: Claude mode with the guard admitting or falling back."""

from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.llm.context import AnalysisContext, AnalystOutput
from app.services.llm.mock import MockAnalyst
from app.services.llm.usage import Usage
from tests.conftest import make_client

FIXTURES = Path(__file__).parent.parent / "fixtures"
JOBS = "/api/v1/jobs"


class FakeClaude:
    """Stands in for ClaudeAnalyst: mock insights plus a known token usage."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, context: AnalysisContext) -> AnalystOutput:
        self.calls += 1
        out = await MockAnalyst(latency_s=0).generate(context)
        usage = Usage(input_tokens=100_000, output_tokens=10_000, calls=3)
        return AnalystOutput(insights=out.insights, usage=usage)


def _upload(client: Any, ip: str) -> dict[str, Any]:
    files = {"file": ("sample.csv", (FIXTURES / "sample.csv").read_bytes())}
    res = client.post(JOBS, files=files, headers={"X-Forwarded-For": f"{ip}, 10.0.0.1"})
    assert res.status_code == 202
    return client.get(f"{JOBS}/{res.json()['job_id']}").json()


def test_claude_runs_are_capped_per_visitor_and_charged(settings: Settings) -> None:
    settings.mock_external = False
    settings.demo_runs_per_hour = 1
    claude = FakeClaude()
    with make_client(settings, analyst=claude, fallback=MockAnalyst(latency_s=0)) as client:
        first = _upload(client, "203.0.113.7")
        assert first["analyst"] == "claude" and first["analyst_note"] is None
        # 100k in at $2/MTok + 10k out at $10/MTok
        assert first["usage"] == {
            "calls": 3,
            "input_tokens": 100_000,
            "output_tokens": 10_000,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": 0.3,
        }

        second = _upload(client, "203.0.113.7")
        assert second["status"] == "completed"
        assert second["analyst"] == "mock" and "per hour" in second["analyst_note"]
        assert second["usage"] is None

        other = _upload(client, "198.51.100.2")  # a different visitor still gets Claude
        assert other["analyst"] == "claude"

        health = client.get("/api/v1/health", headers={"X-Forwarded-For": "203.0.113.7"}).json()
    assert claude.calls == 2
    assert health["demo"]["runs_left_this_hour"] == 0
    assert health["demo"]["budget_remaining_usd"] == 3.0 - 0.6
    assert health["demo"]["claude_available"] is False
