"""Manual smoke test: send the fixture insights to the real Gamma API.

Uses Gamma credits. From apps/api, with GAMMA_API_KEY set:
    .venv/bin/python scripts/smoke_gamma.py
"""

import asyncio
from pathlib import Path

from app.config import get_settings
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.services.gamma.client import GammaClient
from app.services.gamma.formatter import to_gamma_request


async def main() -> None:
    settings = get_settings()
    insights = Insights.model_validate_json(Path("tests/fixtures/llm_response.json").read_text())
    body = to_gamma_request(insights, AnalysisOptions(), "sample.csv", settings.gamma_image_source)
    client = GammaClient(
        settings.gamma_api_key,
        settings.gamma_base_url,
        settings.gamma_timeout_s,
        settings.gamma_poll_interval_s,
    )
    try:
        generation_id = await client.create_generation(body)
        print(f"generation {generation_id} created; polling...")
        print((await client.wait_for_completion(generation_id)).model_dump_json(indent=2))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
