"""Write JobState JSON fixtures for the web app's tests from the real backend models.

Keeps the frontend's zod schemas honest: if the API contract changes, regenerate
these and the web tests will catch any mismatch. From apps/api:
    .venv/bin/python scripts/export_web_fixtures.py
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.insights import Insights
from app.schemas.job import JobError, JobState
from app.schemas.options import AnalysisOptions
from app.schemas.presentation import Presentation
from app.services.deck.fit import fit_slides
from app.services.deck.resolve import resolve_slides
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset

FIXTURES = Path("tests/fixtures")
OUT = Path("../web/__tests__/fixtures")
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _job() -> JobState:
    job = JobState(
        job_id="job123",
        filename="sample.csv",
        options=AnalysisOptions(num_slides=6),
        created_at=T0,
        updated_at=T0,
    )
    for i, stage in enumerate(job.stages):
        stage.started_at = T0 + timedelta(seconds=i * 10)
    return job


def main() -> None:
    df = load_dataset((FIXTURES / "sample.csv").read_bytes(), "sample.csv", 10**8)
    profile = build_profile(df, 200_000)
    insights = Insights.model_validate_json((FIXTURES / "llm_response.json").read_text())

    running = _job()
    running.status = "running"
    for key in ("ingest", "profile"):
        running.stage(key).status = "done"
    running.stage("analyze").status = "running"
    running.profile = profile

    completed = _job()
    completed.status = "completed"
    for stage in completed.stages:
        stage.status = "done"
    completed.profile, completed.insights = profile, insights
    completed.deck = fit_slides(
        resolve_slides(insights.slides, profile, "sample.csv", today=T0.date())
    )
    completed.presentation = Presentation(
        slide_count=len(completed.deck),
        size_bytes=48_213,
        download_path="/jobs/job123/deck.pptx",
    )

    failed = _job()
    failed.status = "failed"
    for stage in failed.stages[:3]:
        stage.status = "done"
    message = "The slide deck could not be rendered."
    failed.stage("generate_deck").status = "failed"
    failed.stage("generate_deck").message = message
    failed.profile, failed.insights = profile, insights
    failed.error = JobError(stage="generate_deck", code="DECK_RENDER_ERROR", message=message)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, job in (("running", running), ("completed", completed), ("failed", failed)):
        (OUT / f"job-{name}.json").write_text(job.model_dump_json(indent=2) + "\n")
        print(f"wrote {OUT / f'job-{name}.json'}")


if __name__ == "__main__":
    main()
