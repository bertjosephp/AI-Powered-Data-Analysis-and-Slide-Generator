"""Offline stand-in for ClaudeAnalyst (MOCK_EXTERNAL=true).

Builds plausible insights from the real profile, deterministically, so demos and
E2E tests show dataset-specific content without an API key.
"""

import asyncio

from app.schemas.insights import (
    AnalyticalQuestion,
    Hypothesis,
    Insights,
    KeyFinding,
    SlideOutline,
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

        body = [
            *(
                SlideOutline(title=f.title, bullets=[f.detail, *f.supporting_stats])
                for f in findings
            ),
            SlideOutline(title="Hypotheses to test", bullets=[h.statement for h in hypotheses]),
            SlideOutline(title="Open questions", bullets=[q.question for q in questions]),
            SlideOutline(
                title="Data quality", bullets=profile.warnings[:5] or ["No major issues."]
            ),
        ][: max(options.num_slides - 3, 1)]
        slides = [
            SlideOutline(
                title=f"Analysis of {dataset_name}", bullets=[f"Prepared for {options.audience}"]
            ),
            SlideOutline(title="Executive summary", bullets=[findings[0].detail]),
            *body,
            SlideOutline(title="Next steps", bullets=[q.question for q in questions[:3]]),
        ]
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
            slide_outline=slides[: options.num_slides],
        )


def _direction(r: float) -> str:
    return "positively" if r > 0 else "negatively"
