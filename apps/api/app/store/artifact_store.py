"""Rendered deck files, keyed by job id. In-memory like the JobStore; same TTL."""

from datetime import datetime, timedelta
from typing import Protocol

from app.schemas.job import utcnow


class ArtifactStore(Protocol):
    def put(self, job_id: str, data: bytes) -> None: ...

    def get(self, job_id: str) -> bytes | None: ...


class InMemoryArtifactStore:
    def __init__(self, ttl_s: int) -> None:
        self._ttl = timedelta(seconds=ttl_s)
        self._items: dict[str, tuple[datetime, bytes]] = {}

    def put(self, job_id: str, data: bytes) -> None:
        self._purge_expired()
        self._items[job_id] = (utcnow(), data)

    def get(self, job_id: str) -> bytes | None:
        self._purge_expired()
        item = self._items.get(job_id)
        return item[1] if item else None

    def _purge_expired(self) -> None:
        cutoff = utcnow() - self._ttl
        for job_id in [k for k, (created, _) in self._items.items() if created < cutoff]:
            del self._items[job_id]
