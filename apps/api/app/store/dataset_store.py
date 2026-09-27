"""Parsed datasets, kept server-side for the job's lifetime.

The analysis stages and Claude's follow-up tools run against this frame; rows
never leave the backend. In-memory like the other stores, with the same TTL.
"""

from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

from app.schemas.job import utcnow


class DatasetStore(Protocol):
    def put(self, job_id: str, df: pd.DataFrame) -> None: ...

    def get(self, job_id: str) -> pd.DataFrame | None: ...


class InMemoryDatasetStore:
    def __init__(self, ttl_s: int) -> None:
        self._ttl = timedelta(seconds=ttl_s)
        self._items: dict[str, tuple[datetime, pd.DataFrame]] = {}

    def put(self, job_id: str, df: pd.DataFrame) -> None:
        self._purge_expired()
        self._items[job_id] = (utcnow(), df)

    def get(self, job_id: str) -> pd.DataFrame | None:
        self._purge_expired()
        item = self._items.get(job_id)
        return item[1] if item else None

    def _purge_expired(self) -> None:
        cutoff = utcnow() - self._ttl
        for job_id in [k for k, (created, _) in self._items.items() if created < cutoff]:
            del self._items[job_id]
