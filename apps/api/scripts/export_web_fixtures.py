"""Write JobState JSON fixtures for the web app's tests from the real backend.

Runs the actual pipeline pieces (profile, findings battery, mock analyst,
grounding, deck resolution) on the e-commerce sample, so the frontend's zod
schemas and components are tested against genuine API output. From apps/api:
    .venv/bin/python scripts/export_web_fixtures.py
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.job import JobError, JobState
from app.schemas.options import AnalysisOptions
from app.schemas.presentation import Presentation
from app.services.analysis.battery import run_battery
from app.services.deck.fit import fit_slides
from app.services.deck.resolve import resolve_slides
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.context import AnalysisContext
from app.services.llm.grounding import check_grounding
from app.services.llm.mock import MockAnalyst

DATA = Path("app/sample_data")
OUT = Path("../web/__tests__/fixtures")
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
FILENAME = "ecommerce_orders.csv"
OPTIONS = AnalysisOptions(
    num_slides=8,
    question="What is hurting our margin, and where are returns coming from?",
    target_column="returned",
)


def _job() -> JobState:
    job = JobState(
        job_id="job123", filename=FILENAME, options=OPTIONS, created_at=T0, updated_at=T0
    )
    for i, stage in enumerate(job.stages):
        stage.started_at = T0 + timedelta(seconds=i * 10)
    return job


def main() -> None:
    df = load_dataset((DATA / FILENAME).read_bytes(), FILENAME, 10**8)
    profile = build_profile(df, 200_000)
    battery = run_battery(df, profile, target="returned")
    context = AnalysisContext(
        profile=profile,
        findings=battery.findings,
        roles=battery.roles,
        options=OPTIONS,
        dataset_name=FILENAME,
    )
    insights = asyncio.run(MockAnalyst(latency_s=0).generate(context)).insights

    running = _job()
    running.status = "running"
    for key in ("ingest", "profile"):
        running.stage(key).status = "done"
    running.stage("explore").status = "running"
    running.profile = profile

    completed = _job()
    completed.status = "completed"
    for stage in completed.stages:
        stage.status = "done"
    completed.profile, completed.roles = profile, battery.roles
    completed.findings = battery.findings
    completed.insights = insights
    completed.grounding = check_grounding(insights, profile, battery.findings)
    completed.deck = fit_slides(
        resolve_slides(
            insights.slides, profile, FILENAME, today=T0.date(), findings=battery.findings
        )
    )
    completed.presentation = Presentation(
        slide_count=len(completed.deck), size_bytes=48_213, download_path="/jobs/job123/deck.pptx"
    )

    failed = completed.model_copy(deep=True)
    failed.status = "failed"
    message = "The slide deck could not be rendered."
    failed.stage("generate_deck").status = "failed"
    failed.stage("generate_deck").message = message
    failed.deck, failed.presentation = None, None
    failed.error = JobError(stage="generate_deck", code="DECK_RENDER_ERROR", message=message)

    OUT.mkdir(parents=True, exist_ok=True)
    # A small, hand-checkable profile for the dataset-profile component tests.
    small = load_dataset(Path("tests/fixtures/sample.csv").read_bytes(), "sample.csv", 10**8)
    (OUT / "profile-small.json").write_text(
        build_profile(small, 200_000).model_dump_json(indent=2) + "\n"
    )
    for name, job in (("running", running), ("completed", completed), ("failed", failed)):
        (OUT / f"job-{name}.json").write_text(job.model_dump_json(indent=2) + "\n")
        print(f"wrote {OUT / f'job-{name}.json'}")


if __name__ == "__main__":
    main()
