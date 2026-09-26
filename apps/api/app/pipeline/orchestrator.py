"""Runs a job through profile -> analyze -> generate_deck, recording progress.

Ingest happens in the upload request so bad files fail fast with a 400; the
parsed DataFrame is handed to `run` and dropped once the profile exists. Each
stage's output is saved on the job, so `run` on a failed job resumes from the
first stage without output.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pandas as pd
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.schemas.job import JobError, JobState, StageKey, utcnow
from app.schemas.presentation import Presentation
from app.services.eda.profiler import build_profile
from app.services.gamma.client import GammaGenerator
from app.services.gamma.formatter import to_gamma_request
from app.services.llm.analyst import InsightsGenerator
from app.store.job_store import JobStore

log = logging.getLogger(__name__)


class _StageFailed(Exception):
    """Raised after a stage failure has been recorded on the job."""


class Pipeline:
    def __init__(
        self,
        store: JobStore,
        analyst: InsightsGenerator,
        gamma: GammaGenerator,
        settings: Settings,
    ) -> None:
        self._store = store
        self._analyst = analyst
        self._gamma = gamma
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
                await self._generate_deck(job)
        except _StageFailed:
            return

        job.status = "completed"
        self._store.save(job)

    async def _generate_deck(self, job: JobState) -> None:
        assert job.insights is not None
        # A pending generation (e.g. one that timed out) is resumed rather than
        # re-created, so a retry doesn't pay for a second deck.
        if job.presentation is None or job.presentation.status == "failed":
            body = to_gamma_request(
                job.insights, job.options, job.filename, self._settings.gamma_image_source
            )
            generation_id = await self._gamma.create_generation(body)
            job.presentation = Presentation(gamma_generation_id=generation_id, status="pending")
            self._store.save(job)

        job.presentation = await self._gamma.wait_for_completion(
            job.presentation.gamma_generation_id
        )
        if job.presentation.status == "failed":
            raise AppError(
                ErrorCode.GAMMA_ERROR,
                f"Gamma could not generate the deck: {job.presentation.error}",
            )

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
