"""Slide deck schemas.

`SlideSpec` is what Claude writes: layouts, prose, and *references* to numbers
(`MetricRef`, `ChartRef`). It never contains a figure. `ResolvedSlide` is what
renderers draw: the same slides with every reference replaced by values taken
from the DatasetProfile (see services/deck/resolve.py).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


def _layout(name: str) -> Any:
    # Structured outputs don't enforce `const` (the SDK moves it into the
    # description), but they do enforce `enum`, so pin the discriminator with both.
    return Field(json_schema_extra={"enum": [name]})


DatasetMetric = Literal["rows", "columns", "missing_cells_pct", "duplicate_rows"]
ColumnMetric = Literal[
    "mean", "median", "min", "max", "std", "unique_count", "missing_pct", "top_value_share"
]
ChartKind = Literal["correlations", "top_values", "missing_values", "numeric_summary"]


class MetricRef(BaseModel):
    """A number to show. Dataset metrics take column=null; column metrics name a column."""

    metric: DatasetMetric | ColumnMetric
    column: str | None


class ChartRef(BaseModel):
    """A chart to draw. top_values and numeric_summary need a column; the others take null."""

    chart: ChartKind
    column: str | None


# ---------- what Claude writes ----------


class TitleSlide(BaseModel):
    layout: Literal["title"] = _layout("title")
    title: str
    subtitle: str


class Takeaway(BaseModel):
    title: str
    text: str


class ExecutiveSummarySlide(BaseModel):
    layout: Literal["executive_summary"] = _layout("executive_summary")
    headline: str
    takeaways: list[Takeaway]


class Kpi(BaseModel):
    label: str
    metric: MetricRef


class KpiSlide(BaseModel):
    layout: Literal["kpi_cards"] = _layout("kpi_cards")
    title: str
    kpis: list[Kpi]


class ChartInsightSlide(BaseModel):
    layout: Literal["chart_insight"] = _layout("chart_insight")
    title: str
    bullets: list[str]
    chart: ChartRef


class HypothesisItem(BaseModel):
    statement: str
    test: str
    confidence: Literal["low", "medium", "high"]


class HypothesesSlide(BaseModel):
    layout: Literal["hypotheses"] = _layout("hypotheses")
    title: str
    items: list[HypothesisItem]


class NextStepsSlide(BaseModel):
    layout: Literal["next_steps"] = _layout("next_steps")
    title: str
    steps: list[str]


SlideSpec = Annotated[
    TitleSlide
    | ExecutiveSummarySlide
    | KpiSlide
    | ChartInsightSlide
    | HypothesesSlide
    | NextStepsSlide,
    Field(discriminator="layout"),
]


# ---------- what renderers draw ----------


class ResolvedTitleSlide(TitleSlide):
    meta: str


class ResolvedKpi(BaseModel):
    label: str
    value: str
    caption: str


class ResolvedKpiSlide(BaseModel):
    layout: Literal["kpi_cards"] = "kpi_cards"
    title: str
    kpis: list[ResolvedKpi]


class ResolvedChart(BaseModel):
    kind: ChartKind
    caption: str
    categories: list[str]
    values: list[float]
    value_format: Literal["number", "percent", "correlation"]


class ResolvedChartInsightSlide(BaseModel):
    layout: Literal["chart_insight"] = "chart_insight"
    title: str
    bullets: list[str]
    chart: ResolvedChart | None  # None when the reference couldn't be resolved


ResolvedSlide = Annotated[
    ResolvedTitleSlide
    | ExecutiveSummarySlide
    | ResolvedKpiSlide
    | ResolvedChartInsightSlide
    | HypothesesSlide
    | NextStepsSlide,
    Field(discriminator="layout"),
]
