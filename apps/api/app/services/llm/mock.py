"""Offline stand-in for ClaudeAnalyst (MOCK_EXTERNAL=true).

Builds plausible insights from the real profile, deterministically, so demos and
E2E tests show dataset-specific content without an API key.
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
from app.schemas.insights import (
    AnalyticalQuestion,
    Hypothesis,
    Insights,
    KeyFinding,
)
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile

MOCK_LATENCY_S = 1.0


class MockAnalyst:
    def __init__(self, latency_s: float = MOCK_LATENCY_S) -> None:
        self._latency_s = latency_s

    async def generate(
        self, profile: DatasetProfile, options: AnalysisOptions, dataset_name: str
    ) -> Insights:
        await asyncio.sleep(self._latency_s)
        numeric = [c for c in profile.columns if c.inferred_type == "numeric"]
        categorical = [c for c in profile.columns if c.inferred_type == "categorical"]

        findings = [
            KeyFinding(
                title="Dataset shape",
                detail=f"{profile.n_rows:,} rows across {profile.n_cols} columns.",
                supporting_stats=[f"missing cells: {profile.missing_pct_total}%"],
            )
        ]
        findings += [
            KeyFinding(
                title=f"{p.a} moves with {p.b}",
                detail=f"{p.a} and {p.b} are {_direction(p.r)} correlated.",
                supporting_stats=[f"{p.a} vs {p.b}: r = {p.r}"],
            )
            for p in profile.top_correlations[:3]
        ]
        hypotheses = [
            Hypothesis(
                statement=f"Changes in {p.a} drive changes in {p.b}.",
                rationale=f"Pearson r = {p.r} in the profile.",
                suggested_test=f"Run a controlled comparison or regression of {p.b} on {p.a}.",
                confidence="medium" if abs(p.r) >= 0.7 else "low",
            )
            for p in profile.top_correlations[:3]
        ] or [
            Hypothesis(
                statement="No strong linear relationships exist between numeric fields.",
                rationale="No pair of numeric columns has |r| >= 0.5.",
                suggested_test="Check for non-linear relationships and segment-level effects.",
                confidence="low",
            )
        ]
        questions = [
            AnalyticalQuestion(
                question=f"How does {n.name} differ across {c.name}?",
                why_it_matters="Segment differences point to where to focus.",
            )
            for n, c in zip(numeric[:3], categorical[:3], strict=False)
        ] or [
            AnalyticalQuestion(
                question="What outcome metric should this data be evaluated against?",
                why_it_matters="Without a target, findings stay descriptive.",
            )
        ]

        slides = _slides(profile, options, dataset_name, findings, hypotheses, questions)
        return Insights(
            executive_summary=(
                f"[Mock analysis] {dataset_name} has {profile.n_rows:,} rows and "
                f"{profile.n_cols} columns, with {len(profile.top_correlations)} notable "
                "correlations. Set MOCK_EXTERNAL=false for a real Claude analysis."
            ),
            key_findings=findings,
            hypotheses=hypotheses,
            analytical_questions=questions,
            data_quality_notes=profile.warnings or ["No major data quality issues detected."],
            recommended_next_steps=["Validate the hypotheses above with targeted tests."],
            slides=slides,
        )


def _direction(r: float) -> str:
    return "positively" if r > 0 else "negatively"


def _slides(
    profile: DatasetProfile,
    options: AnalysisOptions,
    dataset_name: str,
    findings: list[KeyFinding],
    hypotheses: list[Hypothesis],
    questions: list[AnalyticalQuestion],
) -> list[SlideSpec]:
    """A deck that exercises every layout, trimmed to the requested length."""
    numeric = next((c for c in profile.columns if c.inferred_type == "numeric"), None)
    categorical = next((c for c in profile.columns if c.inferred_type == "categorical"), None)

    kpis = [
        Kpi(label="Rows", metric=MetricRef(metric="rows", column=None)),
        Kpi(label="Columns", metric=MetricRef(metric="columns", column=None)),
        Kpi(label="Missing cells", metric=MetricRef(metric="missing_cells_pct", column=None)),
    ]
    if numeric:
        kpis.append(
            Kpi(
                label=f"Median {numeric.name}",
                metric=MetricRef(metric="median", column=numeric.name),
            )
        )

    middle: list[SlideSpec] = [
        KpiSlide(layout="kpi_cards", title="The dataset at a glance", kpis=kpis)
    ]
    if profile.top_correlations:
        top = profile.top_correlations[0]
        middle.append(
            ChartInsightSlide(
                layout="chart_insight",
                title=f"{top.a} and {top.b} move together",
                bullets=[
                    f"The strongest pair is {top.a} and {top.b} (r = {top.r}).",
                    "Treat these as leads to test, not causes.",
                ],
                chart=ChartRef(chart="correlations", column=None),
            )
        )
    if categorical:
        middle.append(
            ChartInsightSlide(
                layout="chart_insight",
                title=f"How {categorical.name} breaks down",
                bullets=[f"{categorical.name} has {categorical.unique_count} distinct values."],
                chart=ChartRef(chart="top_values", column=categorical.name),
            )
        )
    if numeric:
        middle.append(
            ChartInsightSlide(
                layout="chart_insight",
                title=f"The spread of {numeric.name}",
                bullets=[f"Median {numeric.name} is {numeric.median}; the mean is {numeric.mean}."],
                chart=ChartRef(chart="numeric_summary", column=numeric.name),
            )
        )
    if profile.missing_cells_total:
        middle.append(
            ChartInsightSlide(
                layout="chart_insight",
                title="Where the data has gaps",
                bullets=[f"{profile.missing_pct_total}% of all cells are missing."],
                chart=ChartRef(chart="missing_values", column=None),
            )
        )
    middle.append(
        HypothesesSlide(
            layout="hypotheses",
            title="Hypotheses worth testing",
            items=[
                HypothesisItem(
                    statement=h.statement, test=h.suggested_test, confidence=h.confidence
                )
                for h in hypotheses[:3]
            ],
        )
    )

    first: list[SlideSpec] = [
        TitleSlide(
            layout="title",
            title=f"What {dataset_name} tells us",
            subtitle=f"[Mock analysis] Prepared for {options.audience}",
        ),
        ExecutiveSummarySlide(
            layout="executive_summary",
            headline=findings[0].detail,
            takeaways=[Takeaway(title=f.title, text=f.detail) for f in (findings * 3)[:3]],
        ),
    ]
    last = NextStepsSlide(
        layout="next_steps",
        title="Recommended next steps",
        steps=[q.question for q in questions[:3]]
        + ["Validate the hypotheses with targeted tests."],
    )
    return [*first, *middle[: max(options.num_slides - 3, 0)], last]
