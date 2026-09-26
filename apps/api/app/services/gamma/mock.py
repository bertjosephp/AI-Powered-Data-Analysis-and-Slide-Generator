"""Offline stand-in for GammaClient (MOCK_EXTERNAL=true)."""

import asyncio
import hashlib
import json
from typing import Any

from app.schemas.presentation import Presentation

MOCK_LATENCY_S = 2.0


class MockGammaClient:
    def __init__(self, latency_s: float = MOCK_LATENCY_S) -> None:
        self._latency_s = latency_s

    async def aclose(self) -> None:
        pass

    async def create_generation(self, body: dict[str, Any]) -> str:
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return f"mock-{digest[:12]}"

    async def wait_for_completion(self, generation_id: str) -> Presentation:
        await asyncio.sleep(self._latency_s)
        return Presentation(
            gamma_generation_id=generation_id,
            status="completed",
            gamma_url=f"https://gamma.app/docs/{generation_id}",
            export_url=None,
            credits_deducted=0,
            mock=True,
        )
