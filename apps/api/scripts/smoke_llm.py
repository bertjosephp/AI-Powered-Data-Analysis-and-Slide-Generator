"""Manual end-to-end run with the real Claude API: profile, findings battery,
Claude with follow-up tools, grounding check, and the rendered deck.

From apps/api, with ANTHROPIC_API_KEY set (costs a few cents per run):
    .venv/bin/python scripts/smoke_llm.py app/sample_data/saas_churn.csv \\
        --question "Why do customers churn?" --target churned --out deck.pptx
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from app.config import get_settings
from app.schemas.options import AnalysisOptions
from app.services.analysis.battery import run_battery
from app.services.deck.fit import fit_slides
from app.services.deck.pptx_renderer import PptxRenderer
from app.services.deck.resolve import resolve_slides
from app.services.deck.theme import Theme
from app.services.eda.profiler import build_profile, sample_frame
from app.services.ingestion.loader import load_dataset
from app.services.llm.analyst import ClaudeAnalyst
from app.services.llm.client import make_anthropic_client
from app.services.llm.context import AnalysisContext
from app.services.llm.grounding import check_grounding


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    path = Path(args.path)
    df = load_dataset(path.read_bytes(), path.name, settings.max_upload_bytes)
    profile = build_profile(df, settings.profile_sample_rows)
    sample = sample_frame(df, settings.profile_sample_rows)
    battery = run_battery(sample, profile, target=args.target)
    print(f"{len(battery.findings)} findings; targets {battery.roles.targets}", file=sys.stderr)

    options = AnalysisOptions(
        question=args.question, target_column=args.target, num_slides=args.slides
    )
    context = AnalysisContext(
        profile=profile,
        findings=battery.findings,
        roles=battery.roles,
        options=options,
        dataset_name=path.name,
        frame=battery.frame,
    )
    analyst = ClaudeAnalyst(make_anthropic_client(settings), settings.llm_model)
    start = time.perf_counter()
    output = await analyst.generate(context)
    elapsed = time.perf_counter() - start
    findings = [*battery.findings, *output.follow_ups]

    print(output.insights.model_dump_json(indent=2))
    for f in output.follow_ups:
        print(f"follow-up {f.id}: {f.summary}", file=sys.stderr)
    grounding = check_grounding(output.insights, profile, findings)
    print(
        f"\n{settings.llm_model}: {elapsed:.1f}s, {output.tool_calls} tool calls, "
        f"{grounding.checked} numbers checked, {len(grounding.unverified)} unverified",
        file=sys.stderr,
    )
    for u in grounding.unverified:
        print(f"  unverified {u.value} at {u.location}: {u.context}", file=sys.stderr)

    slides = fit_slides(
        resolve_slides(output.insights.slides, profile, path.name, findings=findings)
    )
    Path(args.out).write_bytes(
        PptxRenderer(Theme(font=settings.deck_font)).render(slides, path.name)
    )
    print(f"Deck with {len(slides)} slides written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", nargs="?", default="app/sample_data/ecommerce_orders.csv")
    parser.add_argument("--question")
    parser.add_argument("--target")
    parser.add_argument("--slides", type=int, default=10)
    parser.add_argument("--out", default="deck.pptx")
    asyncio.run(main(parser.parse_args()))
