"""Deterministic text budgets per layout, so nothing overflows its box.

Layouts are drawn at fixed sizes; these limits are what those boxes hold at the
theme's type sizes. Structured outputs can't enforce string lengths, so the
prompt states the budgets and this pass guarantees them.
"""

import logging

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
