"""Deterministic text budgets per layout, so nothing overflows its box.

Layouts are drawn at fixed sizes; these limits are what those boxes hold at the
theme's type sizes. Structured outputs can't enforce string lengths, so the
prompt states the budgets and this pass guarantees them.
"""

import logging
import math

from app.schemas.deck import (
    ExecutiveSummarySlide,
    HypothesesSlide,
    NextStepsSlide,
    ResolvedChartInsightSlide,
    ResolvedKpiSlide,
    ResolvedSlide,
    ResolvedTitleSlide,
)

log = logging.getLogger(__name__)

TITLE = 56
SUBTITLE = 120
HEADLINE = 140
CARD_TITLE = 40
CARD_TEXT = 160
KPI_LABEL = 32
BULLET = 100
STATEMENT = 120
STEP = 110
CHART_CAPTION = 70
CHART_CAPTION_WITH_NOTE = 52
CHART_CATEGORY = 28
MAX_TAKEAWAYS = 3
MAX_KPIS = 4
MAX_BULLETS = 3
MAX_HYPOTHESES = 3
MAX_STEPS = 4

ELLIPSIS = "…"


def clip(text: str, limit: int) -> str:
    """Trim to `limit` characters on a word boundary, ending with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.-–—") + ELLIPSIS


def cap[T](items: list[T], limit: int, what: str) -> list[T]:
    if len(items) > limit:
        log.info("Dropping %d extra %s", len(items) - limit, what)
    return items[:limit]


def fit_slides(slides: list[ResolvedSlide]) -> list[ResolvedSlide]:
    return [fit_slide(s) for s in slides]


def fit_slide(slide: ResolvedSlide) -> ResolvedSlide:
    match slide:
        case ResolvedTitleSlide():
            return slide.model_copy(
                update={
                    "title": clip(slide.title, TITLE),
                    "subtitle": clip(slide.subtitle, SUBTITLE),
                }
            )
        case ExecutiveSummarySlide():
            takeaways = [
                t.model_copy(
                    update={"title": clip(t.title, CARD_TITLE), "text": clip(t.text, CARD_TEXT)}
                )
                for t in cap(slide.takeaways, MAX_TAKEAWAYS, "takeaways")
            ]
            return slide.model_copy(
                update={"headline": clip(slide.headline, HEADLINE), "takeaways": takeaways}
            )
        case ResolvedKpiSlide():
            kpis = [
                k.model_copy(update={"label": clip(k.label, KPI_LABEL)})
                for k in cap(slide.kpis, MAX_KPIS, "KPIs")
            ]
            return slide.model_copy(update={"title": clip(slide.title, TITLE), "kpis": kpis})
        case ResolvedChartInsightSlide():
            bullets = [clip(b, BULLET) for b in cap(slide.bullets, MAX_BULLETS, "bullets")]
            chart = slide.chart
            if chart is not None:
                budget = CHART_CAPTION_WITH_NOTE if chart.reference is not None else CHART_CAPTION
                chart = chart.model_copy(
                    update={
                        "caption": clip(chart.caption, budget),
                        "categories": [clip(c, CHART_CATEGORY) for c in chart.categories],
                    }
                )
            return slide.model_copy(
                update={"title": clip(slide.title, TITLE), "bullets": bullets, "chart": chart}
            )
        case HypothesesSlide():
            items = [
                h.model_copy(
                    update={
                        "statement": clip(h.statement, STATEMENT),
                        "test": clip(h.test, STATEMENT),
                    }
                )
                for h in cap(slide.items, MAX_HYPOTHESES, "hypotheses")
            ]
            return slide.model_copy(update={"title": clip(slide.title, TITLE), "items": items})
        case NextStepsSlide():
            steps = [clip(s, STEP) for s in cap(slide.steps, MAX_STEPS, "steps")]
            return slide.model_copy(update={"title": clip(slide.title, TITLE), "steps": steps})
    return slide


# ---------- font size to fit a box ----------
#
# Character budgets keep text short, but whether it fits depends on how the words
# wrap: "Clinical risk concentrates predictably" is only 38 characters yet needs
# three lines in a narrow card. The renderer therefore estimates the wrapped height
# and steps the font size down until the text fits. Glyph widths are averages for
# the deck's sans-serif fonts, erring wide so the estimate is conservative.

EMU_PER_PT = 12_700
GLYPH_WIDTH = 0.55  # average advance, in ems, for regular weight
BOLD_GLYPH_WIDTH = 0.6
LINE_HEIGHT = 1.2  # of the font size, before paragraph line spacing
MIN_SCALE = 0.7  # never shrink below 70% of the design size


def wrapped_lines(text: str, width_pt: float, size: float, *, bold: bool) -> int:
    """How many lines `text` wraps to in a box `width_pt` wide, breaking at spaces."""
    per_line = max(int(width_pt / (size * (BOLD_GLYPH_WIDTH if bold else GLYPH_WIDTH))), 1)
    lines = 0
    for paragraph in text.split("\n"):
        lines += 1
        used = 0
        for word in paragraph.split():
            needed = len(word) if used == 0 else used + 1 + len(word)
            if needed <= per_line:
                used = needed
            else:
                # The word starts a new line; one longer than a whole line wraps mid-word.
                extra = max(math.ceil(len(word) / per_line) - 1, 0)
                lines += 1 + extra if used else extra
                used = len(word) - extra * per_line
    return lines


def size_to_fit(
    text: str,
    width_emu: int,
    height_emu: int,
    size: int,
    *,
    bold: bool = False,
    line_spacing: float = 1.1,
) -> int:
    """The largest size, from `size` down to MIN_SCALE of it, at which `text` fits."""
    width_pt, height_pt = width_emu / EMU_PER_PT, height_emu / EMU_PER_PT
    floor = max(int(size * MIN_SCALE), 8)
    for candidate in range(size, floor - 1, -1):
        lines = wrapped_lines(text, width_pt, candidate, bold=bold)
        if lines * candidate * LINE_HEIGHT * line_spacing <= height_pt:
            return candidate
    return floor
