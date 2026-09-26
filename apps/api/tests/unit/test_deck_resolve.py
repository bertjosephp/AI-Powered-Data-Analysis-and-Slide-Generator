from datetime import date
from pathlib import Path

import pytest

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
    ResolvedChartInsightSlide,
    ResolvedKpiSlide,
    ResolvedTitleSlide,
    Takeaway,
    TitleSlide,
)
from app.schemas.profile import DatasetProfile
from app.services.deck.fit import ELLIPSIS, clip, fit_slides
from app.services.deck.resolve import (
    find_column,
    format_number,
    format_percent,
    resolve_chart,
    resolve_metric,
    resolve_slides,
)
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def profile() -> DatasetProfile:
    df = load_dataset((FIXTURES / "sample.csv").read_bytes(), "sample.csv", 10**8)
    return build_profile(df, 200_000)


def _col(profile: DatasetProfile, name: str):  # type: ignore[no-untyped-def]
    return next(c for c in profile.columns if c.name == name)


# ---------- metrics ----------


@pytest.mark.parametrize(
    ("metric", "column", "expected"),
    [
        ("rows", None, ("40", "rows in the dataset")),
        ("columns", None, ("9", "columns profiled")),
        ("missing_cells_pct", None, ("1.4%", "of all cells are missing")),
        ("duplicate_rows", None, ("0", "fully duplicated rows")),
        ("median", "revenue", ("463", "median of revenue")),
        ("unique_count", "product", ("3", "distinct values of product")),
        ("missing_pct", "discount", ("7.5%", "of discount is missing")),
        ("top_value_share", "region", ("34.2%", "of region is South")),  # 13 of 38 non-missing
        ("mean", "REVENUE", ("685", "mean of revenue")),  # case-insensitive column match
    ],
)
def test_metrics_resolve_from_the_profile(profile, metric, column, expected) -> None:  # type: ignore[no-untyped-def]
    assert (
        resolve_metric(MetricRef(metric=metric, column=column, finding_id=None), profile)
        == expected
    )


def test_metric_values_match_profile_exactly(profile) -> None:  # type: ignore[no-untyped-def]
    value, _ = resolve_metric(MetricRef(metric="max", column="revenue", finding_id=None), profile)  # type: ignore[misc]
    assert value == format_number(_col(profile, "revenue").max)


@pytest.mark.parametrize(
    ("metric", "column"),
    [
        ("mean", "no_such_column"),
        ("mean", "region"),  # not numeric
        ("top_value_share", "units"),  # numeric columns have no top values
        ("median", None),
    ],
)
def test_unresolvable_metrics_return_none(profile, metric, column) -> None:  # type: ignore[no-untyped-def]
    assert resolve_metric(MetricRef(metric=metric, column=column, finding_id=None), profile) is None


# ---------- charts ----------


def test_correlation_chart_uses_top_pairs(profile) -> None:  # type: ignore[no-untyped-def]
    chart = resolve_chart(ChartRef(chart="correlations", column=None, finding_id=None), profile)
    assert chart is not None
    assert chart.categories == [f"{p.a} × {p.b}" for p in profile.top_correlations]
    assert chart.values == [p.r for p in profile.top_correlations]
    assert chart.value_format == "correlation"


def test_top_values_chart(profile) -> None:  # type: ignore[no-untyped-def]
    chart = resolve_chart(ChartRef(chart="top_values", column="product", finding_id=None), profile)
    assert chart is not None
    assert list(zip(chart.categories, chart.values, strict=True)) == [
        ("Gizmo", 15.0),
        ("Gadget", 13.0),
        ("Widget", 12.0),
    ]


def test_missing_values_chart_sorted_desc(profile) -> None:  # type: ignore[no-untyped-def]
    chart = resolve_chart(ChartRef(chart="missing_values", column=None, finding_id=None), profile)
    assert chart is not None
    assert chart.categories == ["discount", "region"] and chart.values == [7.5, 5.0]


def test_numeric_summary_chart(profile) -> None:  # type: ignore[no-untyped-def]
    units = _col(profile, "units")
    chart = resolve_chart(
        ChartRef(chart="numeric_summary", column="units", finding_id=None), profile
    )
    assert chart is not None
    assert chart.categories == ["Min", "P25", "Median", "P75", "Max"]
    assert chart.values == [units.min, units.p25, units.median, units.p75, units.max]


@pytest.mark.parametrize(
    ("chart", "column"),
    [
        ("top_values", "revenue"),
        ("numeric_summary", "region"),
        ("top_values", "nope"),
        ("top_values", None),
    ],
)
def test_unresolvable_charts_return_none(profile, chart, column) -> None:  # type: ignore[no-untyped-def]
    assert resolve_chart(ChartRef(chart=chart, column=column, finding_id=None), profile) is None


def test_chart_degrades_when_dataset_has_no_signal(profile) -> None:  # type: ignore[no-untyped-def]
    empty = profile.model_copy(update={"top_correlations": []})
    assert (
        resolve_chart(ChartRef(chart="correlations", column=None, finding_id=None), empty) is None
    )


# ---------- whole deck ----------


def test_resolve_slides_replaces_every_reference(profile) -> None:  # type: ignore[no-untyped-def]
    slides = [
        TitleSlide(layout="title", title="Sales review", subtitle="What drives revenue"),
        KpiSlide(
            layout="kpi_cards",
            title="At a glance",
            kpis=[
                Kpi(label="Orders", metric=MetricRef(metric="rows", column=None, finding_id=None)),
                Kpi(
                    label="Bogus", metric=MetricRef(metric="mean", column="ghost", finding_id=None)
                ),
            ],
        ),
        ChartInsightSlide(
            layout="chart_insight",
            title="Price drives revenue",
            bullets=["r = 0.78"],
            chart=ChartRef(chart="top_values", column="ghost", finding_id=None),
        ),
        NextStepsSlide(layout="next_steps", title="Next", steps=["Do it"]),
    ]
    out = resolve_slides(slides, profile, "sample.csv", today=date(2026, 9, 26))

    assert isinstance(out[0], ResolvedTitleSlide)
    assert out[0].meta == "sample.csv · 40 rows × 9 columns · September 2026"
    assert isinstance(out[1], ResolvedKpiSlide)
    assert [(k.label, k.value) for k in out[1].kpis] == [("Orders", "40")]  # bogus KPI dropped
    assert isinstance(out[2], ResolvedChartInsightSlide) and out[2].chart is None  # text-only
    assert out[3] == slides[3]


def test_find_column_prefers_exact_match(profile) -> None:  # type: ignore[no-untyped-def]
    assert find_column(profile, "units") is _col(profile, "units")
    assert find_column(profile, " Units ") is _col(profile, "units")
    assert find_column(profile, None) is None


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (40, "40"),
        (1234, "1,234"),
        (12_500, "12.5K"),
        (3_400_000, "3.4M"),
        (685.06275, "685"),
        (26.625, "26.62"),
        (0.144865, "0.145"),
        (2.0, "2"),
    ],
)
def test_format_number(value: float, text: str) -> None:
    assert format_number(value) == text


def test_format_percent() -> None:
    assert (format_percent(7.5), format_percent(5.0), format_percent(1.39)) == (
        "7.5%",
        "5%",
        "1.4%",
    )


# ---------- fit ----------


def test_clip_trims_on_word_boundary() -> None:
    assert clip("short", 10) == "short"
    text = "Revenue is driven far more by product mix than by order volume across regions"
    out = clip(text, 40)
    assert len(out) <= 40 and out.endswith(ELLIPSIS)
    assert out == "Revenue is driven far more by product…"
    assert clip("  collapses   inner   whitespace ", 50) == "collapses inner whitespace"


def test_fit_enforces_budgets_and_counts() -> None:
    long = "word " * 80
    slides = fit_slides(
        [
            ExecutiveSummarySlide(
                layout="executive_summary",
                headline=long,
                takeaways=[Takeaway(title=long, text=long) for _ in range(5)],
            ),
            HypothesesSlide(
                layout="hypotheses",
                title=long,
                items=[HypothesisItem(statement=long, test=long, confidence="low")] * 4,
            ),
            NextStepsSlide(layout="next_steps", title="Next", steps=[long] * 6),
        ]
    )
    summary, hyps, steps = slides
    assert isinstance(summary, ExecutiveSummarySlide)
    assert len(summary.headline) <= 140 and len(summary.takeaways) == 3
    assert all(len(t.title) <= 40 and len(t.text) <= 160 for t in summary.takeaways)
    assert isinstance(hyps, HypothesesSlide) and len(hyps.items) == 3 and len(hyps.title) <= 60
    assert isinstance(steps, NextStepsSlide) and len(steps.steps) == 4
