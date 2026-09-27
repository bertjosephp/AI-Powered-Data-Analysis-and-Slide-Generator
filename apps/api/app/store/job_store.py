"""Job persistence. In-memory for the MVP; swap in a DB-backed JobStore later."""

from datetime import timedelta
from typing import Protocol

from app.schemas.job import JobState, utcnow


class JobStore(Protocol):
    def create(self, job: JobState) -> None: ...

    def get(self, job_id: str) -> JobState | None: ...

    def save(self, job: JobState) -> None: ...


class InMemoryJobStore:
    """Holds jobs for `ttl_s` after their last update. Not shared across processes,
    so run a single uvicorn worker."""

    def __init__(self, ttl_s: int) -> None:
        self._ttl = timedelta(seconds=ttl_s)
        self._jobs: dict[str, JobState] = {}

    def create(self, job: JobState) -> None:
        self._purge_expired()
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> JobState | None:
        self._purge_expired()
        job = self._jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    def save(self, job: JobState) -> None:
        job.updated_at = utcnow()
        self._jobs[job.job_id] = job.model_copy(deep=True)

    def _purge_expired(self) -> None:
        cutoff = utcnow() - self._ttl
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.updated_at < cutoff and job.status in ("completed", "failed")
        ]
        for job_id in expired:
            del self._jobs[job_id]
