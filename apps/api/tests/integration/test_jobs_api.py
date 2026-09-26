"""End-to-end through the HTTP API with the LLM faked and the real deck renderer.

TestClient runs background tasks before returning the response, so the pipeline
has finished by the time POST /jobs returns.
"""

import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pptx import Presentation as PptxFile

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.schemas.deck import ResolvedSlide
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile
from app.services.llm.mock import MockAnalyst
from tests.conftest import make_client

FIXTURES = Path(__file__).parent.parent / "fixtures"
JOBS = "/api/v1/jobs"


def _upload(client: TestClient, name: str = "sample.csv", **kwargs: Any) -> Any:
    files = {"file": (name, (FIXTURES / name).read_bytes())}
    return client.post(JOBS, files=files, **kwargs)


def _stage_statuses(job: dict[str, Any]) -> dict[str, str]:
    return {s["key"]: s["status"] for s in job["stages"]}


class CountingAnalyst:
    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self.failures = failures

    async def generate(
        self, profile: DatasetProfile, options: AnalysisOptions, dataset_name: str
    ) -> Insights:
        self.calls += 1
        if self.calls <= self.failures:
            raise AppError(ErrorCode.LLM_ERROR, "Anthropic rate limit reached. Retry later.")
        return await MockAnalyst(latency_s=0).generate(profile, options, dataset_name)


class FlakyRenderer:
    """Fails the first `failures` renders, then renders for real."""

    def __init__(self, failures: int) -> None:
        self.calls = 0
        self.failures = failures

    def render(self, slides: list[ResolvedSlide], dataset_name: str) -> bytes:
        from app.services.deck.pptx_renderer import PptxRenderer

        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("renderer exploded")
        return PptxRenderer().render(slides, dataset_name)


# ---------- happy path ----------


def test_full_pipeline_completes(client: TestClient) -> None:
    res = _upload(client, data={"options": json.dumps({"num_slides": 6, "audience": "the board"})})
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    job = client.get(f"{JOBS}/{job_id}").json()
    assert job["status"] == "completed"
    assert _stage_statuses(job) == {
        "ingest": "done",
        "profile": "done",
        "analyze": "done",
        "generate_deck": "done",
    }
    assert job["filename"] == "sample.csv"
    assert job["options"]["audience"] == "the board"
    assert job["profile"]["n_rows"] == 40
    assert len(job["insights"]["slides"]) == 6
    assert [s["layout"] for s in job["deck"]][:3] == ["title", "executive_summary", "kpi_cards"]
    assert job["deck"][2]["kpis"][0] == {
        "label": "Rows",
        "value": "40",
        "caption": "rows in the dataset",
    }
    assert job["presentation"]["slide_count"] == 6
    assert job["presentation"]["download_path"] == f"/jobs/{job_id}/deck.pptx"
    assert job["error"] is None

    profile = client.get(f"{JOBS}/{job_id}/profile")
    assert profile.status_code == 200 and profile.json()["n_cols"] == 9


def test_xlsx_upload_completes(client: TestClient) -> None:
    job_id = _upload(client, "sample.xlsx").json()["job_id"]
    assert client.get(f"{JOBS}/{job_id}").json()["status"] == "completed"


# ---------- synchronous validation ----------


def test_corrupt_file_is_rejected_with_error_envelope(client: TestClient) -> None:
    res = client.post(JOBS, files={"file": ("bad.xlsx", b"not a workbook")})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_FILE"


def test_unsupported_extension_is_rejected(client: TestClient) -> None:
    res = client.post(JOBS, files={"file": ("data.json", b"{}")})
    assert res.status_code == 400 and res.json()["error"]["code"] == "INVALID_FILE"


def test_oversized_file_is_rejected(settings: Settings) -> None:
    settings.max_upload_mb = 1
    with make_client(settings) as client:
        res = client.post(JOBS, files={"file": ("big.csv", b"a,b\n" + b"1,2\n" * 300_000)})
    assert res.status_code == 413 and res.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_invalid_options_are_rejected(client: TestClient) -> None:
    res = _upload(client, data={"options": json.dumps({"num_slides": 99})})
    assert res.status_code == 400
    body = res.json()["error"]
    assert body["code"] == "INVALID_OPTIONS" and "num_slides" in body["message"]


def test_missing_file_is_a_validation_error(client: TestClient) -> None:
    res = client.post(JOBS)
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_job_is_404(client: TestClient) -> None:
    res = client.get(f"{JOBS}/nope")
    assert res.status_code == 404 and res.json()["error"]["code"] == "JOB_NOT_FOUND"


# ---------- failures and retry ----------


def test_llm_failure_then_retry_reuses_profile(settings: Settings) -> None:
    analyst = CountingAnalyst(failures=1)
    with make_client(settings, analyst=analyst) as client:
        job_id = _upload(client).json()["job_id"]
        failed = client.get(f"{JOBS}/{job_id}").json()
        assert failed["status"] == "failed"
        assert _stage_statuses(failed)["analyze"] == "failed"
        assert failed["error"] == {
            "stage": "analyze",
            "code": "LLM_ERROR",
            "message": "Anthropic rate limit reached. Retry later.",
        }
        profiled_at = failed["stages"][1]["finished_at"]

        assert client.post(f"{JOBS}/{job_id}/retry").status_code == 202
        done = client.get(f"{JOBS}/{job_id}").json()

    assert done["status"] == "completed" and done["error"] is None
    assert done["stages"][1]["finished_at"] == profiled_at  # profile was not recomputed
    assert analyst.calls == 2


def test_render_failure_then_retry_renders_again(settings: Settings) -> None:
    analyst = CountingAnalyst()
    renderer = FlakyRenderer(failures=1)
    with make_client(settings, analyst=analyst, renderer=renderer) as client:
        job_id = _upload(client).json()["job_id"]
        failed = client.get(f"{JOBS}/{job_id}").json()
        assert failed["error"] == {
            "stage": "generate_deck",
            "code": "DECK_RENDER_ERROR",
            "message": "The slide deck could not be rendered.",
        }
        assert client.get(f"{JOBS}/{job_id}/deck.pptx").status_code == 409

        client.post(f"{JOBS}/{job_id}/retry")
        done = client.get(f"{JOBS}/{job_id}").json()
        assert done["status"] == "completed"
        assert client.get(f"{JOBS}/{job_id}/deck.pptx").status_code == 200

    assert analyst.calls == 1  # insights were not regenerated
    assert renderer.calls == 2


# ---------- deck download ----------


def test_deck_download_is_a_valid_pptx(client: TestClient) -> None:
    job_id = _upload(client, data={"options": json.dumps({"num_slides": 8})}).json()["job_id"]
    res = client.get(f"{JOBS}/{job_id}/deck.pptx")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert 'filename="sample-deck.pptx"' in res.headers["content-disposition"]
    deck = PptxFile(io.BytesIO(res.content))
    job = client.get(f"{JOBS}/{job_id}").json()
    assert len(deck.slides) == job["presentation"]["slide_count"]
    assert len(res.content) == job["presentation"]["size_bytes"]


def test_deck_download_for_unknown_job_is_404(client: TestClient) -> None:
    res = client.get(f"{JOBS}/nope/deck.pptx")
    assert res.status_code == 404 and res.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_retry_of_completed_job_is_rejected(client: TestClient) -> None:
    job_id = _upload(client).json()["job_id"]
    res = client.post(f"{JOBS}/{job_id}/retry")
    assert res.status_code == 409 and res.json()["error"]["code"] == "JOB_NOT_RETRYABLE"
