"""Manual smoke test: profile a file and ask Claude for real insights.

Usage (from apps/api, with ANTHROPIC_API_KEY set):
    .venv/bin/python scripts/smoke_llm.py tests/fixtures/sample.csv
"""

import asyncio
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.schemas.options import AnalysisOptions
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.analyst import ClaudeAnalyst
from app.services.llm.client import make_anthropic_client


async def main(path: Path) -> None:
    settings = get_settings()
    df = load_dataset(path.read_bytes(), path.name, settings.max_upload_bytes)
    profile = build_profile(df, settings.profile_sample_rows)
    analyst = ClaudeAnalyst(make_anthropic_client(settings), settings.llm_model)

    start = time.perf_counter()
    insights = await analyst.generate(profile, AnalysisOptions(), path.name)
    print(insights.model_dump_json(indent=2))
    print(f"\n{settings.llm_model}: {time.perf_counter() - start:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample.csv")))
