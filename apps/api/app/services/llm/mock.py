"""Offline stand-in for ClaudeAnalyst (MOCK_EXTERNAL=true).

Builds the report and deck deterministically from the battery's findings, so
offline demos and E2E tests still tell a real story, just without Claude's
follow-up analysis or prose.
"""

import asyncio

from app.schemas.deck import (
    ChartInsightSlide,
    ChartRef,
    ExecutiveSummarySlide,
    HypothesesSlide,
    HypothesisItem,
    Kpi,
    KpiSlide,
    MetricRef,
    NextStepsSlide,
    SlideSpec,
    Takeaway,
    TitleSlide,
)
from app.schemas.findings import Finding
from app.schemas.insights import (
    AnsweredQuestion,
    Hypothesis,
    Insights,
    KeyFinding,
    OpenQuestion,
)
from app.services.llm.context import AnalysisContext, AnalystOutput

MOCK_LATENCY_S = 1.0
MOCK_NOTE = "[Mock analysis] "


class MockAnalyst:
    def __init__(self, latency_s: float = MOCK_LATENCY_S) -> None:
        self._latency_s = latency_s

    async def generate(self, context: AnalysisContext) -> AnalystOutput:
        await asyncio.sleep(self._latency_s)
        return AnalystOutput(insights=_insights(context))


def _insights(ctx: AnalysisContext) -> Insights:
    findings = ctx.findings
    story = [f for f in findings if f.kind != "drivers"]
    drivers = next((f for f in findings if f.kind == "drivers"), None)
    target = ctx.roles.targets[0] if ctx.roles.targets else "the outcome"
    question = ctx.options.question or f"What drives {target}?"
    lead = story[:3]

    summary = (
        MOCK_NOTE + " ".join(f.summary for f in lead)
        if lead
        else MOCK_NOTE + f"{ctx.dataset_name} has no statistically significant patterns to report."
    )
    answer_sources = [f for f in [drivers, *lead[:2]] if f is not None]
    answered = [
        AnsweredQuestion(
            question=question,
            answer=" ".join(f.summary for f in answer_sources) or "No clear drivers were found.",
            finding_ids=[f.id for f in answer_sources],
            confidence="medium" if lead else "low",
        )
    ]
    hypotheses = [
        Hypothesis(
            statement=f"{f.dimension} influences {f.target}.",
            rationale=f.summary,
            test=f"Run a controlled comparison (or A/B test) varying {f.dimension} "
            f"and measure {f.target}.",
            finding_ids=[f.id],
            confidence="medium" if f.effect.strength == "strong" else "low",
        )
        for f in story
        if f.kind in ("segment", "bins") and f.dimension
    ][:3]
    return Insights(
        executive_summary=summary,
        key_findings=[
            KeyFinding(title=f.title, detail=f.summary, finding_ids=[f.id]) for f in story[:5]
        ],
        questions_answered=answered,
        open_questions=[
            OpenQuestion(
                question=f"Does the {f.dimension} effect on {f.target} hold within each segment?",
                why_it_matters="Confounding between segments can create or hide an effect.",
            )
            for f in story[:2]
            if f.dimension
        ],
        hypotheses=hypotheses,
        recommended_actions=[f"Investigate: {f.title}." for f in story[:3]],
        data_quality_notes=list(ctx.profile.warnings[:3]),
        slides=_slides(ctx, story, hypotheses, target),
    )


def _slides(
    ctx: AnalysisContext, story: list[Finding], hypotheses: list[Hypothesis], target: str
) -> list[SlideSpec]:
    first: list[SlideSpec] = [
        TitleSlide(
            layout="title",
            title=f"What drives {target}",
            subtitle=MOCK_NOTE + (ctx.options.question or f"Prepared for {ctx.options.audience}"),
        ),
        ExecutiveSummarySlide(
            layout="executive_summary",
            headline=story[0].summary
            if story
            else f"No significant patterns in {ctx.dataset_name}.",
            takeaways=[Takeaway(title=f.title, text=f.summary) for f in story[:3]],
        ),
    ]
    kpis = [
        Kpi(label=_kpi_label(f), metric=MetricRef(metric="finding", column=None, finding_id=f.id))
        for f in story[:4]
    ] or [Kpi(label="Rows", metric=MetricRef(metric="rows", column=None, finding_id=None))]
    middle: list[SlideSpec] = [
        KpiSlide(layout="kpi_cards", title="The numbers that matter", kpis=kpis)
    ]
    middle += [
        ChartInsightSlide(
            layout="chart_insight",
            title=f.title,
            bullets=[f.summary, *f.caveats[:1]],
            chart=ChartRef(chart="finding", column=None, finding_id=f.id),
        )
        for f in story
    ]
    hypotheses_slide = (
        HypothesesSlide(
            layout="hypotheses",
            title="What to test next",
            items=[
                HypothesisItem(statement=h.statement, test=h.test, confidence=h.confidence)
                for h in hypotheses
            ],
        )
        if hypotheses
        else None
    )
    last = NextStepsSlide(
        layout="next_steps",
        title="Recommended next steps",
        steps=[f"Act on: {f.title}." for f in story[:3]]
        or ["Collect more data and re-run the analysis."],
    )
    room = max(ctx.options.num_slides - len(first) - 1, 1)
    if hypotheses_slide is not None and room >= 3:
        middle = [*middle[: room - 1], hypotheses_slide]
    return [*first, *middle[:room], last]


def _kpi_label(f: Finding) -> str:
    label = f"{f.target} by {f.dimension}" if f.dimension else f.target
    return label[:30]
