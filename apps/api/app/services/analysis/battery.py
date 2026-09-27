"""The automatic analysis battery: a fixed plan of analyses, FDR-controlled and ranked.

For each target (the user's, or up to two inferred ones):
  1. driver ranking over every column
  2. segment comparisons for the strongest categorical drivers
  3. binned breakdowns for the strongest numeric drivers
  4. trend (and seasonality) over the date column
Plus, dataset-wide:
  5. record-volume trend
  6. concentration of the main value measure across entities (Pareto)
  7. a scan of every other measure × dimension for large, significant gaps

All p-values from every test run (including screening tests that did not become
findings) are adjusted together with Benjamini-Hochberg, so a big battery
doesn't manufacture false discoveries.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

import pandas as pd

from app.schemas.findings import ColumnRoles, Finding
from app.schemas.profile import DatasetProfile
from app.services.analysis import stats
from app.services.analysis.analyses import (
    ROWS,
    AnalysisError,
    Frame,
    compare_segments,
    concentration,
    driver_ranking,
    driver_tests,
    metric_by_bins,
    trend,
)
from app.services.analysis.roles import infer_roles

log = logging.getLogger(__name__)

MAX_FINDINGS = 15
SEGMENTS_PER_TARGET = 6  # candidates; ranking decides which survive
BINS_PER_TARGET = 8
SCAN_FINDINGS = 4
Q_THRESHOLD = 0.05
# Scan pairs this strong are nearly always definitional (unit price by category,
# seats by plan) rather than insight, so the scan skips them.
STRUCTURAL_EPSILON_SQUARED = 0.45
STRUCTURAL_RATE_RATIO = 8.0
DUPLICATE_DIMENSION_V = 0.9
_GENERIC_TOKENS = {
    "id",
    "num",
    "count",
    "total",
    "avg",
    "pct",
    "rate",
    "score",
    "days",
    "is",
    "has",
}


@dataclass
class BatteryResult:
    roles: ColumnRoles
    findings: list[Finding]
    tests_run: int
    frame: Frame = field(repr=False)


def make_frame(df: pd.DataFrame, roles: ColumnRoles, sampled_from: int | None = None) -> Frame:
    return Frame(
        df=df, binaries=frozenset(roles.binaries), time=roles.time, sampled_from=sampled_from
    )


def run_battery(
    df: pd.DataFrame,
    profile: DatasetProfile,
    target: str | None = None,
    sampled_from: int | None = None,
) -> BatteryResult:
    roles = infer_roles(df, profile, target)
    frame = make_frame(df, roles, sampled_from)
    candidates: list[tuple[Finding, float]] = []  # (finding, priority weight)
    screening_p: list[float | None] = []

    def attempt(weight: float, build: Callable[[], Finding]) -> None:
        try:
            candidates.append((build(), weight))
        except AnalysisError as e:
            log.info("Battery skipped an analysis: %s", e)

    for rank, tgt in enumerate(roles.targets):
        weight = 1.3 if rank == 0 else 1.1
        # A later target must not be "explained" by an earlier one (circular); the
        # primary target may still use a secondary one as a driver.
        others = frozenset(roles.targets[:rank])
        dims = [d for d in roles.dimensions if d != tgt]
        measures = [m for m in roles.measures if m != tgt]
        tests, _ = driver_tests(frame, tgt, dims, measures, others)
        screening_p.extend(t.result.p_value for t in tests)
        attempt(weight * 0.9, partial(driver_ranking, frame, tgt, dims, measures, others))

        useful = [
            t for t in tests if t.result.p_value is not None and t.result.p_value < Q_THRESHOLD
        ]
        used_dims: list[str] = []
        for t in [t for t in useful if t.kind == "dimension"][:SEGMENTS_PER_TARGET]:
            if any(_same_split(frame, t.column, d) for d in used_dims):
                continue
            used_dims.append(t.column)
            attempt(weight, partial(compare_segments, frame, tgt, t.column))
        for t in [t for t in useful if t.kind == "measure"][:BINS_PER_TARGET]:
            attempt(weight, partial(metric_by_bins, frame, tgt, t.column))
        if roles.time:
            attempt(weight, partial(trend, frame, tgt))

    if roles.time:
        attempt(0.8, partial(trend, frame, ROWS))
    if roles.value_measure and roles.entity:
        attempt(1.0, partial(concentration, frame, roles.value_measure, roles.entity))

    if roles.targets:
        _explain_drivers(frame, roles, roles.targets[0], candidates, screening_p, attempt)
    relevance = _relevance(frame, roles)
    candidates.extend(_scan(frame, roles, screening_p, relevance))

    findings = _adjust_and_rank(candidates, screening_p)
    return BatteryResult(
        roles=roles, findings=findings, tests_run=len(screening_p) + len(candidates), frame=frame
    )


EXPLAINED_DRIVERS = 2


def _explain_drivers(
    frame: Frame,
    roles: ColumnRoles,
    target: str,
    candidates: list[tuple[Finding, float]],
    screening_p: list[float | None],
    attempt: Callable[[float, Callable[[], Finding]], None],
) -> None:
    """Second-order findings: what drives the strongest numeric drivers of the target.

    "Returns fall as ratings rise" becomes a story once it is followed by
    "and ratings are lowest where shipping is slowest".
    """
    tests, _ = driver_tests(
        frame, target, roles.dimensions, roles.measures, frozenset(roles.targets)
    )
    top_measures = [
        t.column
        for t in tests
        if t.kind == "measure" and t.result.p_value is not None and t.result.p_value < Q_THRESHOLD
    ][:EXPLAINED_DRIVERS]
    exclude = frozenset(roles.targets)
    for driver in top_measures:
        sub_tests, _ = driver_tests(
            frame,
            driver,
            [d for d in roles.dimensions if not _shares_name(d, driver)],
            [m for m in roles.measures if not _shares_name(m, driver)],
            exclude,
        )
        screening_p.extend(t.result.p_value for t in sub_tests)
        significant = [
            t for t in sub_tests if t.result.p_value is not None and t.result.p_value < Q_THRESHOLD
        ]
        dim = next(
            (
                t
                for t in significant
                if t.kind == "dimension"
                and not (
                    t.result.effect_name == "epsilon squared"
                    and t.result.effect > STRUCTURAL_EPSILON_SQUARED
                )
            ),
            None,
        )
        measure = next((t for t in significant if t.kind == "measure"), None)
        if dim is not None:
            attempt(0.85, partial(compare_segments, frame, driver, dim.column))
        if measure is not None:
            attempt(0.85, partial(metric_by_bins, frame, driver, measure.column))


def _relevance(frame: Frame, roles: ColumnRoles) -> dict[str, float]:
    """How strongly each column relates to any target (0..1), to weight scan findings."""
    out: dict[str, float] = {}
    for tgt in roles.targets:
        tests, _ = driver_tests(frame, tgt, roles.dimensions, roles.measures)
        for t in tests:
            out[t.column] = max(out.get(t.column, 0.0), t.result.association)
    return out


def _scan(
    frame: Frame,
    roles: ColumnRoles,
    screening_p: list[float | None],
    relevance: dict[str, float],
) -> list[tuple[Finding, float]]:
    """Large gaps in non-target measures across dimensions (e.g. 'West ships 3 days slower')."""
    scored: list[tuple[float, float, str, str]] = []
    components = {c for t in roles.targets for c in _components(frame, t, roles.measures)}
    others = [
        m
        for m in [*roles.measures, *roles.binaries]
        if m not in roles.targets and m not in components
    ]
    for metric in others:
        for dim in roles.dimensions:
            if dim == metric or dim in roles.targets or _shares_name(metric, dim):
                continue
            try:
                y = frame.df[metric]
                groups = frame.df[dim].map(lambda v: None if pd.isna(v) else str(v))
                data = pd.DataFrame({"y": y, "g": groups}).dropna()
                counts = data["g"].value_counts()
                data = data[data["g"].isin(counts[counts >= frame.min_group].index)]
                if data["g"].nunique() < 2:
                    continue
                if metric in roles.binaries:
                    yb = data["y"].astype(str).str.casefold().isin(["true", "1", "yes", "1.0"])
                    result = stats.binary_by_groups(yb.astype(float), data["g"])
                else:
                    result = stats.numeric_by_groups(
                        pd.to_numeric(data["y"], errors="coerce").fillna(0), data["g"]
                    )
            except (ValueError, TypeError):
                continue
            screening_p.append(result.p_value)
            if _structural(result, data, metric in roles.binaries):
                continue
            if result.p_value is not None and result.strength in ("moderate", "strong"):
                weight = _scan_weight(relevance.get(metric, 0.0))
                raw = stats.normalized(result.effect_name, result.effect)
                scored.append((min(raw, 1.0) * weight, raw, metric, dim))
    scored.sort(reverse=True)

    out: list[tuple[Finding, float]] = []
    used: set[str] = set()
    for _, _, metric, dim in scored:
        if len(out) >= SCAN_FINDINGS:
            break
        if metric in used:  # one finding per measure keeps the list varied
            continue
        try:
            out.append(
                (compare_segments(frame, metric, dim), _scan_weight(relevance.get(metric, 0.0)))
            )
            used.add(metric)
        except AnalysisError:
            continue
    return out


def _scan_weight(relevance: float) -> float:
    """Scan findings matter more when the measure itself relates to an outcome."""
    return 0.55 + 0.35 * min(relevance / 0.3, 1.0)


def _components(frame: Frame, target: str, measures: list[str]) -> list[str]:
    from app.services.analysis.analyses import components_of

    return components_of(frame, target, measures)


def _shares_name(a: str, b: str) -> bool:
    def tokens(name: str) -> set[str]:
        return {
            t for t in name.lower().replace("-", "_").split("_") if t and t not in _GENERIC_TOKENS
        }

    return bool(tokens(a) & tokens(b))


def _structural(result: stats.TestResult, data: pd.DataFrame, binary: bool) -> bool:
    if result.effect_name == "epsilon squared":
        return result.effect > STRUCTURAL_EPSILON_SQUARED
    if binary:
        yb = data["y"].astype(str).str.casefold().isin(["true", "1", "yes", "1.0"])
        rates = yb.astype(float).groupby(data["g"]).mean()
        return bool(
            (rates <= 0.005).any()
            or (rates >= 0.995).any()
            or result.effect >= STRUCTURAL_RATE_RATIO
        )
    return False


def _same_split(frame: Frame, a: str, b: str) -> bool:
    """Two dimensions that split rows (almost) identically, e.g. diagnosis and department."""
    pair = frame.df[[a, b]].dropna().astype(str)
    return stats.categorical_vs_categorical(pair[a], pair[b]).effect >= DUPLICATE_DIMENSION_V


def _adjust_and_rank(
    candidates: list[tuple[Finding, float]], screening_p: list[float | None]
) -> list[Finding]:
    p_values = [f.p_value for f, _ in candidates]
    q_all = stats.benjamini_hochberg([*p_values, *screening_p])
    kept: list[Finding] = []
    seen: set[tuple[frozenset[str], str]] = set()
    for (finding, weight), q in zip(candidates, q_all[: len(candidates)], strict=True):
        finding.q_value = None if q is None else float(f"{q:.3g}")
        if finding.p_value is not None:
            finding.significant = (
                finding.q_value is not None
                and finding.q_value < Q_THRESHOLD
                and finding.effect.strength != "negligible"
            )
        # Unordered pair: "logins by last-login" and "last-login by logins" are one finding.
        key = (frozenset((finding.target, finding.dimension or "")), finding.kind)
        mirror = (
            frozenset((finding.target, finding.dimension or "")),
            "bins" if finding.kind == "segment" else "segment",
        )
        if not finding.significant or key in seen or (finding.kind == "bins" and mirror in seen):
            continue
        seen.add(key)
        cap = 1.0 if weight < 1.0 else 1.5  # scan findings can't outrank strong target findings
        finding.score = round(
            min(stats.normalized(finding.effect.name, finding.effect.value), cap) * weight, 4
        )
        kept.append(finding)
    kept.sort(key=lambda f: f.score, reverse=True)
    kept = kept[:MAX_FINDINGS]
    for i, finding in enumerate(kept, start=1):
        finding.id = f"F{i}"
    return kept
