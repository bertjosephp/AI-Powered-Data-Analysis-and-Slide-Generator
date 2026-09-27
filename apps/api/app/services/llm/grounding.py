"""Check that the numbers in Claude's prose come from the evidence.

Every figure in the insights and slides is matched, within the precision it is
printed at, against the numbers in the profile and findings, plus simple
comparisons between them (a gap in points, a ratio). Unmatched figures are
reported, not removed: they may be legitimate arithmetic, but a reader
should know they weren't computed by the analysis engine.
"""

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.schemas.findings import Finding
from app.schemas.insights import GroundingReport, Insights, UnverifiedNumber
from app.schemas.profile import DatasetProfile

# A number not glued to a word (so "F12", "readmitted_30d", "Q4" are skipped).
_NUMBER = re.compile(
    r"(?<![\w.])([-+−]?\d{1,3}(?:,\d{3})+|[-+−]?\d+(?:\.\d+)?)\s*(%|×|x\b|[KMB]\b|pp\b|points?\b)?(?![\w])"
)
_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9}
SMALL_INTEGER = 12  # counts like "3 takeaways" or "top 10" aren't statistics


@dataclass
class Evidence:
    """Numbers the analysis produced, kept apart by kind so a figure printed as a
    percentage is only matched against percentages, a ratio against ratios."""

    numbers: set[float] = field(default_factory=set)
    percents: set[float] = field(default_factory=set)
    ratios: set[float] = field(default_factory=set)

    def add_text(self, text: str) -> None:
        for m in _NUMBER.finditer(text):
            value, _ = _parse(m.group(1), m.group(2))
            if value is not None:
                self.pool(m.group(2)).add(abs(value))

    def pool(self, unit: str | None) -> set[float]:
        if unit in ("%", "pp", "point", "points"):
            return self.percents
        if unit in ("×", "x"):
            return self.ratios
        return self.numbers


def check_grounding(
    insights: Insights, profile: DatasetProfile, findings: list[Finding]
) -> GroundingReport:
    evidence = _evidence(profile, findings)
    checked = 0
    unverified: list[UnverifiedNumber] = []
    for location, text in _texts(insights.model_dump()):
        for match in _NUMBER.finditer(text):
            unit = match.group(2)
            value, decimals = _parse(match.group(1), unit)
            if value is None or _ignorable(value, decimals, unit):
                continue
            checked += 1
            if not _supported(value, decimals, unit, evidence):
                start = max(0, match.start() - 40)
                unverified.append(
                    UnverifiedNumber(
                        location=location,
                        value=match.group(0).strip(),
                        context=text[start : match.end() + 40].strip(),
                    )
                )
    return GroundingReport(checked=checked, unverified=unverified)


def _texts(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in (
                "finding_ids",
                "finding_id",
                "layout",
                "metric",
                "chart",
                "column",
                "confidence",
            ):
                continue
            yield from _texts(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _texts(value, f"{path}[{i}]")


def _parse(raw: str, unit: str | None) -> tuple[float | None, int]:
    cleaned = raw.replace(",", "").replace("−", "-")
    try:
        value = float(cleaned)
    except ValueError:
        return None, 0
    decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
    if unit in _SCALE:
        value *= _SCALE[unit]
    return value, decimals


def _ignorable(value: float, decimals: int, unit: str | None) -> bool:
    if unit is None and decimals == 0 and abs(value) <= SMALL_INTEGER:
        return True
    return unit is None and decimals == 0 and 1900 <= value <= 2100  # years


def _supported(value: float, decimals: int, unit: str | None, evidence: Evidence) -> bool:
    # Only the rounding implied by how the number is printed ("18%" matches 17.6).
    tolerance = abs(value) * 0.05 if unit in _SCALE else 10 ** (-decimals) / 2 + 1e-9
    target = abs(value)
    if unit in ("%", "pp", "point", "points"):
        pools = [evidence.percents]
    elif unit in ("×", "x"):
        pools = [evidence.ratios]
    else:
        pools = [evidence.numbers, evidence.percents]
    return any(abs(target - e) <= tolerance for pool in pools for e in pool)


def _evidence(profile: DatasetProfile, findings: list[Finding]) -> Evidence:
    ev = Evidence()
    ev.percents.add(profile.missing_pct_total)
    for col in profile.columns:
        ev.percents.add(col.missing_pct)
        for key, value in col.model_dump(exclude={"name", "missing_pct"}).items():
            if (
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                ev.numbers.add(abs(float(value)))
            elif key == "top_values" and value:
                ev.numbers.update(float(v["count"]) for v in value)
    for pair in profile.top_correlations:
        ev.numbers.add(abs(pair.r))
    for finding in findings:
        _add_finding(ev, finding)
    return ev


def _add_finding(ev: Evidence, f: Finding) -> None:
    for text in (f.summary, f.headline, f.title, *f.caveats):
        ev.add_text(text)
    ev.numbers.add(abs(f.effect.value))
    if f.effect.name == "rate ratio":
        ev.ratios.add(abs(f.effect.value))
    percent = f.chart.value_format == "percent"
    chart_pool = ev.percents if percent else ev.numbers
    chart_pool.update(abs(v) for v in f.chart.values if math.isfinite(v))
    if f.chart.reference is not None:
        chart_pool.add(abs(f.chart.reference))
    for value in f.facts.values():
        if isinstance(value, int | float) and math.isfinite(value):
            chart_pool.add(abs(float(value)))
            if abs(value) <= 1:  # shares (concentration) printed as percentages
                ev.percents.add(abs(float(value)) * 100)
    _add_comparisons(ev, f, chart_pool)


def _add_comparisons(ev: Evidence, finding: Finding, pool: set[float]) -> None:
    """Comparisons a writer naturally makes from one finding: each group against the
    overall value, the top against the bottom, and the first band against the last."""
    values = [v for v in finding.chart.values if math.isfinite(v)]
    pairs: list[tuple[float, float]] = []
    if finding.chart.reference is not None:
        pairs += [(v, finding.chart.reference) for v in values]
    if values:
        pairs.append((max(values), min(values)))
        pairs.append((values[0], values[-1]))
    for a, b in pairs:
        pool.add(abs(a - b))  # a gap, in the chart's own unit (points for rates)
        for num, den in ((a, b), (b, a)):
            if den:
                ev.ratios.add(abs(num / den))
                ev.percents.add(abs(num / den - 1) * 100)
