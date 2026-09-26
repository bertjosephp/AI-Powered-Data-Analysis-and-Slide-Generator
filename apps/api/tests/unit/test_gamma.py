import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from tenacity import wait_none

from app.errors import AppError, ErrorCode
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.services.gamma.client import GammaClient
from app.services.gamma.formatter import CARD_BREAK, to_gamma_request
from app.services.gamma.mock import MockGammaClient

BASE = "https://gamma.test/v1.0"
FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def insights() -> Insights:
    return Insights.model_validate_json((FIXTURES / "llm_response.json").read_text())


@pytest.fixture
async def client() -> AsyncIterator[GammaClient]:
    c = GammaClient("sk-test", BASE, timeout_s=0.2, poll_interval_s=0.01, retry_wait=wait_none())
    yield c
    await c.aclose()


# ---------- formatter ----------


def test_formatter_builds_one_card_per_slide(insights: Insights) -> None:
    body = to_gamma_request(
        insights, AnalysisOptions(theme_id="t1", export_as="pptx"), "s.csv", "noImages"
    )
    cards = body["inputText"].split(CARD_BREAK)
    assert len(cards) == body["numCards"] == len(insights.slide_outline) == 6
    assert cards[0].startswith("# Sales Performance Review")
    assert "- unit_price vs revenue: r = 0.78" in cards[2]
    assert body["cardSplit"] == "inputTextBreaks"
    assert body["format"] == "presentation"
    assert body["themeId"] == "t1" and body["exportAs"] == "pptx"
    assert body["imageOptions"] == {"source": "noImages"}
    assert body["textOptions"]["audience"] == "business stakeholders"


def test_formatter_omits_optional_fields(insights: Insights) -> None:
    body = to_gamma_request(insights, AnalysisOptions(export_as=None), "s.csv", "noImages")
    assert "themeId" not in body and "exportAs" not in body


# ---------- client ----------


@respx.mock
async def test_create_then_poll_until_completed(client: GammaClient) -> None:
    create = respx.post(f"{BASE}/generations").respond(200, json={"generationId": "g1"})
    respx.get(f"{BASE}/generations/g1").mock(
        side_effect=[
            httpx.Response(200, json={"generationId": "g1", "status": "pending"}),
            httpx.Response(
                200,
                json={
                    "generationId": "g1",
                    "status": "completed",
                    "gammaUrl": "https://gamma.app/docs/g1",
                    "exportUrl": "https://export/g1.pdf",
                    "credits": {"deducted": 42, "remaining": 100},
                },
            ),
        ]
    )

    gen_id = await client.create_generation({"inputText": "x"})
    result = await client.wait_for_completion(gen_id)

    assert gen_id == "g1"
    assert create.calls[0].request.headers["X-API-KEY"] == "sk-test"
    assert json.loads(create.calls[0].request.content) == {"inputText": "x"}
    assert (result.status, result.gamma_url, result.export_url) == (
        "completed",
        "https://gamma.app/docs/g1",
        "https://export/g1.pdf",
    )
    assert result.credits_deducted == 42


@respx.mock
async def test_failed_generation_is_returned_with_error(client: GammaClient) -> None:
    respx.get(f"{BASE}/generations/g1").respond(
        200, json={"status": "failed", "error": {"message": "bad input", "statusCode": 400}}
    )
    result = await client.wait_for_completion("g1")
    assert (result.status, result.error) == ("failed", "bad input")


@respx.mock
async def test_times_out_while_pending(client: GammaClient) -> None:
    respx.get(f"{BASE}/generations/g1").respond(200, json={"status": "pending"})
    with pytest.raises(AppError) as exc:
        await client.wait_for_completion("g1")
    assert exc.value.code == ErrorCode.GAMMA_TIMEOUT


@pytest.mark.parametrize(
    ("status", "fragment"),
    [(401, "key was rejected"), (402, "out of credits"), (400, "rejected the request")],
)
@respx.mock
async def test_create_maps_http_errors(client: GammaClient, status: int, fragment: str) -> None:
    route = respx.post(f"{BASE}/generations").respond(status, json={"message": "details here"})
    with pytest.raises(AppError) as exc:
        await client.create_generation({})
    assert exc.value.code == ErrorCode.GAMMA_ERROR
    assert fragment in exc.value.message and "details here" in exc.value.message
    assert route.call_count == 1  # client errors are never retried


@respx.mock
async def test_create_retries_429(client: GammaClient) -> None:
    route = respx.post(f"{BASE}/generations").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"generationId": "g2"})]
    )
    assert await client.create_generation({}) == "g2"
    assert route.call_count == 2


@respx.mock
async def test_create_does_not_retry_500(client: GammaClient) -> None:
    route_500 = respx.post(f"{BASE}/generations").respond(500)
    with pytest.raises(AppError):
        await client.create_generation({})
    assert route_500.call_count == 1  # a 500 may have created a deck; don't duplicate it


@respx.mock
async def test_poll_retries_transient_errors(client: GammaClient) -> None:
    route = respx.get(f"{BASE}/generations/g1").mock(
        side_effect=[
            httpx.ConnectError("down"),
            httpx.Response(503),
            httpx.Response(200, json={"status": "completed", "gammaUrl": "u"}),
        ]
    )
    result = await client.wait_for_completion("g1")
    assert result.gamma_url == "u" and route.call_count == 3


async def test_mock_client_completes_with_mock_flag() -> None:
    mock = MockGammaClient(latency_s=0)
    gen_id = await mock.create_generation({"inputText": "x"})
    result = await mock.wait_for_completion(gen_id)
    assert result.mock and result.status == "completed" and gen_id in (result.gamma_url or "")
