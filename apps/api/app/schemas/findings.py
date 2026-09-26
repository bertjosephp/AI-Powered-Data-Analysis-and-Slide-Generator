"""Statistically tested findings: the evidence the story is built on.

Every number in a Finding is computed by the analysis engine
(services/analysis). `summary` and `headline` are templated from those
numbers, so they are safe to show and to cite.
"""

from typing import Literal

from pydantic import BaseModel

FindingKind = Literal["segment", "trend", "bins", "drivers", "concentration", "crosstab"]
Strength = Literal["negligible", "weak", "moderate", "strong"]
ValueFormat = Literal["number", "percent", "correlation", "currency"]


class Effect(BaseModel):
    name: str  # e.g. "rate ratio", "epsilon squared", "Spearman rho"
    value: float
    strength: Strength


class FindingChart(BaseModel):
    kind: Literal["bars", "line", "ranking"]
    categories: list[str]
    values: list[float]
    value_format: ValueFormat
    reference: float | None = None  # overall value, drawn as a reference line
    reference_label: str | None = None
    counts: list[int] | None = None  # rows behind each bar


class Finding(BaseModel):
    id: str
    kind: FindingKind
    title: str
    summary: str
    headline: str  # the one value worth putting on a KPI card, e.g. "2.4×"
    target: str
    dimension: str | None = None
    agg: str
    effect: Effect
    p_value: float | None = None
    q_value: float | None = None  # Benjamini-Hochberg across the battery
    n: int
    significant: bool
    chart: FindingChart
    caveats: list[str] = []
    filter: str | None = None  # human-readable subset, e.g. "plan = Enterprise"
    source: Literal["battery", "follow_up"] = "battery"
    score: float = 0.0
    # Machine-readable specifics (top/bottom group, band values, peak months, shares).
    facts: dict[str, str | float | list[str]] = {}


class ColumnRoles(BaseModel):
    time: str | None
    measures: list[str]
    dimensions: list[str]
    binaries: list[str]
    entity: str | None
    value_measure: str | None
    targets: list[str]
