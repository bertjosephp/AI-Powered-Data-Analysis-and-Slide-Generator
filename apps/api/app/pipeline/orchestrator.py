"""Runs a job through profile -> explore -> analyze -> generate_deck, recording progress.

Ingest happens in the upload request so bad files fail fast with a 400; the
parsed DataFrame is kept in the DatasetStore for the job's lifetime, so the
analysis stages (and retries of them) can use it. Each stage's output is saved
on the job, so `run` on a failed job resumes from the first stage without output.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pandas as pd
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.schemas.deck import ResolvedSlide
from app.schemas.job import JobError, JobState, JobUsage, StageKey, utcnow
from app.schemas.presentation import Presentation
from app.services.analysis.battery import BatteryResult, make_frame, run_battery
from app.services.analysis.roles import resolve_column
from app.services.deck.fit import fit_slides
from app.services.deck.pptx_renderer import DeckRenderer
from app.services.deck.resolve import resolve_slides
from app.services.eda.profiler import build_profile, sample_frame
from app.services.llm.context import AnalysisContext, InsightsGenerator
from app.services.llm.grounding import check_grounding
from app.services.llm.guard import DemoGuard
from app.services.llm.usage import Usage
from app.store.artifact_store import ArtifactStore
from app.store.dataset_store import DatasetStore
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
        datasets: DatasetStore,
        settings: Settings,
        *,
        fallback: InsightsGenerator | None = None,
        guard: DemoGuard | None = None,
        uses_claude: bool = False,
    ) -> None:
        self._store = store
        self._datasets = datasets
        self._analyst = analyst
        self._fallback = fallback or analyst
        self._guard = guard
        self._uses_claude = uses_claude
        self._reserved: set[str] = set()
        self._renderer = renderer
        self._artifacts = artifacts
        self._settings = settings

    def admit(self, job: JobState, client_id: str) -> None:
        """Choose Claude or the offline analyst for this job, reserving a demo slot."""
        if not self._uses_claude:
            job.analyst, job.analyst_note = "mock", None
            return
        if self._guard is None:
            job.analyst, job.analyst_note = "claude", None
            return
        decision = self._guard.decide(client_id)
        job.analyst = "claude" if decision.use_claude else "mock"
        job.analyst_note = decision.note
        if decision.use_claude:
            self._reserved.add(job.job_id)

    async def run(self, job_id: str) -> None:
        try:
            await self._run(job_id)
        finally:
            if job_id in self._reserved and self._guard is not None:
                self._reserved.discard(job_id)
                job = self._store.get(job_id)
                cost = job.usage.cost_usd if job and job.usage else 0.0
                self._guard.finish(cost)

    async def _run(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job is None:
            log.warning("Job %s vanished before it ran", job_id)
            return
        job.status = "running"
        self._store.save(job)

        try:
            if job.profile is None:
                async with self._stage(job, "profile"):
                    job.profile = await run_in_threadpool(
                        build_profile, self._dataset(job), self._settings.profile_sample_rows
                    )

            if job.findings is None:
                async with self._stage(job, "explore"):
                    result = await run_in_threadpool(self._explore, self._dataset(job), job)
                    job.roles, job.findings = result.roles, result.findings

            if job.insights is None:
                async with self._stage(job, "analyze"):
                    # In mock mode the primary analyst *is* the offline one; otherwise the
                    # fallback serves runs the demo guard didn't admit to Claude.
                    use_primary = job.analyst == "claude" or not self._uses_claude
                    analyst = self._analyst if use_primary else self._fallback
                    try:
                        output = await analyst.generate(self._context(job))
                    except Exception:
                        # Charge whatever the failed attempt spent before re-raising.
                        partial = getattr(analyst, "_usage", None)
                        if partial is not None:
                            job.usage = self._job_usage(partial)
                        raise
                    if output.usage is not None:
                        job.usage = self._job_usage(output.usage)
                    job.findings = [*(job.findings or []), *output.follow_ups]
                    job.insights = output.insights
                    job.grounding = check_grounding(output.insights, job.profile, job.findings)

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

    def _dataset(self, job: JobState) -> pd.DataFrame:
        df = self._datasets.get(job.job_id)
        if df is None:
            raise AppError(
                ErrorCode.DATASET_EXPIRED, "The dataset is no longer in memory. Upload it again."
            )
        return df

    def _job_usage(self, usage: Usage) -> JobUsage:
        cost = usage.cost_usd(
            self._settings.llm_input_usd_per_mtok, self._settings.llm_output_usd_per_mtok
        )
        return JobUsage(
            calls=usage.calls,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=round(cost, 5),
        )

    def _context(self, job: JobState) -> AnalysisContext:
        assert job.profile is not None and job.roles is not None
        df = self._datasets.get(job.job_id)
        frame = None
        if df is not None:  # without the dataset, the analyst works from findings alone
            sample = sample_frame(df, self._settings.profile_sample_rows)
            frame = make_frame(sample, job.roles, len(df) if len(sample) < len(df) else None)
        return AnalysisContext(
            profile=job.profile,
            findings=list(job.findings or []),
            roles=job.roles,
            options=job.options,
            dataset_name=job.filename,
            frame=frame,
        )

    def _explore(self, df: pd.DataFrame, job: JobState) -> BatteryResult:
        assert job.profile is not None
        sample = sample_frame(df, self._settings.profile_sample_rows)
        target = resolve_column(sample, job.options.target_column)
        return run_battery(
            sample,
            job.profile,
            target=target,
            sampled_from=len(df) if len(sample) < len(df) else None,
        )

    def _build_deck(self, job: JobState) -> tuple[list[ResolvedSlide], bytes]:
        """Resolve references against the profile, enforce text budgets, render."""
        assert job.insights is not None and job.profile is not None
        slides = fit_slides(
            resolve_slides(
                job.insights.slides, job.profile, job.filename, findings=job.findings or []
            )
        )
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
