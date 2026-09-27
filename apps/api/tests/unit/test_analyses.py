from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.analysis.analyses import (
    ROWS,
    AnalysisError,
    Frame,
    Where,
    compare_segments,
    components_of,
    concentration,
    crosstab,
    driver_ranking,
    metric_by_bins,
    trend,
)
from app.services.analysis.battery import make_frame
from app.services.analysis.roles import infer_roles
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset

DATA = Path(__file__).parents[2] / "app" / "sample_data"


@cache
def _frame(name: str) -> Frame:
    df = load_dataset((DATA / f"{name}.csv").read_bytes(), f"{name}.csv", 10**8)
    return make_frame(df, infer_roles(df, build_profile(df, 200_000)))


def test_compare_segments_binary_outcome() -> None:
    f = compare_segments(_frame("ecommerce_orders"), "returned", "channel")
    assert f.kind == "segment" and f.agg == "rate"
    assert f.facts["top"] == "Social"
    assert f.chart.value_format == "percent"
    assert f.chart.categories[0] == "Social"  # sorted, highest first
    assert f.chart.reference == pytest.approx(f.facts["overall"])
    assert f.significant and f.effect.name == "rate ratio"
    assert "Social" in f.summary and "%" in f.headline


def test_compare_segments_numeric_and_case_insensitive_columns() -> None:
    f = compare_segments(_frame("ecommerce_orders"), "Shipping_Days", "REGION")
    assert f.target == "shipping_days" and f.dimension == "region"
    assert f.facts["top"] == "West" and f.effect.name == "epsilon squared"


def test_where_filter_restricts_rows_and_is_reported() -> None:
    frame = _frame("saas_churn")
    full = compare_segments(frame, "churned", "billing_cycle")
    sub = compare_segments(frame, "churned", "billing_cycle", where=Where("plan", "basic"))
    assert sub.n < full.n
    assert sub.filter == "plan = Basic"
    assert any("plan = Basic" in c for c in sub.caveats)


def test_bad_requests_raise_analysis_errors() -> None:
    frame = _frame("ecommerce_orders")
    with pytest.raises(AnalysisError, match="Unknown metric"):
        compare_segments(frame, "nope", "region")
    with pytest.raises(AnalysisError, match="No rows where"):
        compare_segments(frame, "returned", "region", where=Where("region", "Mars"))
    with pytest.raises(AnalysisError, match="yes/no"):
        metric_by_bins(frame, "margin", "returned")


def test_bins_direction_and_discrete_tail() -> None:
    frame = _frame("saas_churn")
    tickets = metric_by_bins(frame, "churned", "support_tickets_90d")
    assert tickets.chart.categories[-1].endswith("+")  # sparse tail merged into "k+"
    assert tickets.facts["last_value"] > tickets.facts["first_value"]
    margin = metric_by_bins(_frame("ecommerce_orders"), "margin", "discount_pct")
    assert margin.facts["shape"] == "decreasing"
    assert margin.facts["last_value"] < margin.facts["first_value"] / 2


def test_null_relationship_is_not_significant() -> None:
    f = metric_by_bins(_frame("ecommerce_orders"), "units", "discount_pct")
    assert not f.significant


def test_trend_detects_q4_seasonality() -> None:
    f = trend(_frame("ecommerce_orders"), ROWS)
    assert f.kind == "trend" and f.chart.kind == "line"
    assert set(f.facts["peak_months"]) == {"Nov", "Dec"}
    assert "Nov–Dec" in f.headline


def test_trend_without_date_column() -> None:
    with pytest.raises(AnalysisError, match="no date column"):
        trend(_frame("hr_attrition"), "left_company")


def test_concentration_pareto() -> None:
    f = concentration(_frame("ecommerce_orders"), "revenue", "customer_id")
    assert f.facts["top10_share"] > 0.35
    assert f.chart.categories == ["Top 10%", "Top 20%", "Top 50%"]
    assert f.significant
    with pytest.raises(AnalysisError, match="negative"):
        concentration(_frame("ecommerce_orders"), "margin", "customer_id")


def test_crosstab() -> None:
    f = crosstab(_frame("hr_attrition"), "department", "overtime")
    assert f.kind == "crosstab" and f.effect.name == "Cramer's V"


def test_components_are_excluded_from_drivers() -> None:
    frame = _frame("ecommerce_orders")
    assert set(components_of(frame, "margin", ["revenue", "cost", "units", "discount_pct"])) == {
        "revenue",
        "cost",
    }
    f = driver_ranking(
        frame, "margin", ["region", "channel"], ["revenue", "cost", "discount_pct", "units"]
    )
    assert "revenue" not in f.chart.categories and "cost" not in f.chart.categories
    assert any("components" in c for c in f.caveats)


def test_small_groups_fold_into_other() -> None:
    rng = np.random.default_rng(1)
    n = 400
    df = pd.DataFrame(
        {
            "y": rng.normal(size=n),
            "g": ["big"] * 300 + ["mid"] * 90 + [f"rare{i}" for i in range(10)],
        }
    )
    frame = Frame(df=df, binaries=frozenset(), time=None)
    f = compare_segments(frame, "y", "g")
    assert "rare0" not in f.chart.categories
