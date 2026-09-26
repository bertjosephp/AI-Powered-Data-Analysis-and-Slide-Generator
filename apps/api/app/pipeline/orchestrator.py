"""Runs a job through profile -> analyze -> generate_deck, recording progress.

Ingest happens in the upload request so bad files fail fast with a 400; the
parsed DataFrame is handed to `run` and dropped once the profile exists. Each
stage's output is saved on the job, so `run` on a failed job resumes from the
first stage without output. The deck stage is local and deterministic, so a
retry simply renders again.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pandas as pd
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.schemas.deck import ResolvedSlide
from app.schemas.job import JobError, JobState, StageKey, utcnow
from app.schemas.presentation import Presentation
from app.services.deck.fit import fit_slides
from app.services.deck.pptx_renderer import DeckRenderer
from app.services.deck.resolve import resolve_slides
from app.services.eda.profiler import build_profile
from app.services.llm.analyst import InsightsGenerator
from app.store.artifact_store import ArtifactStore
from app.store.job_store import JobStore

log = logging.getLogger(__name__)


class _StageFailed(Exception):
    """Raised after a stage failure has been recorded on the job."""


class Pipeline:
    def __init__(
        self,
        store: JobStore,
        analyst: InsightsGenerator,
        renderer: DeckRenderer,
        artifacts: ArtifactStore,
        settings: Settings,
    ) -> None:
        self._store = store
        self._analyst = analyst
        self._renderer = renderer
        self._artifacts = artifacts
        self._settings = settings

    async def run(self, job_id: str, df: pd.DataFrame | None = None) -> None:
        job = self._store.get(job_id)
        if job is None:
            log.warning("Job %s vanished before it ran", job_id)
            return
        job.status = "running"
        self._store.save(job)

        try:
            if job.profile is None:
                async with self._stage(job, "profile"):
                    if df is None:
                        raise AppError(
                            ErrorCode.INTERNAL_ERROR,
                            "The dataset is no longer in memory. Upload it again.",
                        )
                    job.profile = await run_in_threadpool(
                        build_profile, df, self._settings.profile_sample_rows
                    )
                df = None

            if job.insights is None:
                async with self._stage(job, "analyze"):
                    job.insights = await self._analyst.generate(
                        job.profile, job.options, job.filename
                    )

            async with self._stage(job, "generate_deck"):
                slides, data = await run_in_threadpool(self._build_deck, job)
                self._artifacts.put(job.job_id, data)
                job.deck = slides
                job.presentation = Presentation(
                    slide_count=len(slides),
                    size_bytes=len(data),
                    download_path=f"/jobs/{job.job_id}/deck.pptx",
                )
        except _StageFailed:
            return

        job.status = "completed"
        self._store.save(job)

    def _build_deck(self, job: JobState) -> tuple[list[ResolvedSlide], bytes]:
        """Resolve references against the profile, enforce text budgets, render."""
        assert job.insights is not None and job.profile is not None
        slides = fit_slides(resolve_slides(job.insights.slides, job.profile, job.filename))
        try:
            return slides, self._renderer.render(slides, job.filename)
        except Exception as e:
            log.exception("Rendering the deck for job %s failed", job.job_id)
            raise AppError(
                ErrorCode.DECK_RENDER_ERROR, "The slide deck could not be rendered."
            ) from e

    @asynccontextmanager
    async def _stage(self, job: JobState, key: StageKey) -> AsyncIterator[None]:
        stage = job.stage(key)
        stage.status = "running"
        stage.started_at, stage.finished_at, stage.message = utcnow(), None, None
        job.error = None
        self._store.save(job)
        try:
            yield
        except AppError as e:
            self._fail(job, key, e.code, e.message)
            raise _StageFailed from e
        except Exception as e:
            log.exception("Job %s failed in stage %s", job.job_id, key)
            self._fail(job, key, ErrorCode.INTERNAL_ERROR, "An unexpected error occurred.")
            raise _StageFailed from e
        stage.status, stage.finished_at = "done", utcnow()
        self._store.save(job)

    def _fail(self, job: JobState, key: StageKey, code: str, message: str) -> None:
        stage = job.stage(key)
        stage.status, stage.finished_at, stage.message = "failed", utcnow(), message
        job.status = "failed"
        job.error = JobError(stage=key, code=code, message=message)
        self._store.save(job)
