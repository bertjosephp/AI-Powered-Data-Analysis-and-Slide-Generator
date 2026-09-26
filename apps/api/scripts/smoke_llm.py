"""Manual smoke test: profile a file, ask Claude for real insights, render the deck.

Usage (from apps/api, with ANTHROPIC_API_KEY set):
    .venv/bin/python scripts/smoke_llm.py tests/fixtures/sample.csv [out.pptx]
"""

import asyncio
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.schemas.options import AnalysisOptions
from app.services.deck.fit import fit_slides
from app.services.deck.pptx_renderer import PptxRenderer
from app.services.deck.resolve import resolve_slides
from app.services.deck.theme import Theme
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.analyst import ClaudeAnalyst
from app.services.llm.client import make_anthropic_client


async def main(path: Path, out: Path) -> None:
    settings = get_settings()
    df = load_dataset(path.read_bytes(), path.name, settings.max_upload_bytes)
    profile = build_profile(df, settings.profile_sample_rows)
    analyst = ClaudeAnalyst(make_anthropic_client(settings), settings.llm_model)

    start = time.perf_counter()
    insights = await analyst.generate(profile, AnalysisOptions(), path.name)
    print(insights.model_dump_json(indent=2))
    print(f"\n{settings.llm_model}: {time.perf_counter() - start:.1f}s", file=sys.stderr)

    slides = fit_slides(resolve_slides(insights.slides, profile, path.name))
    out.write_bytes(PptxRenderer(Theme(font=settings.deck_font)).render(slides, path.name))
    print(f"Deck with {len(slides)} slides written to {out}", file=sys.stderr)


if __name__ == "__main__":
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample.csv")
    asyncio.run(main(source, Path(sys.argv[2] if len(sys.argv) > 2 else "deck.pptx")))
