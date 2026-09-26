"""The analyses. Each takes the (sampled) DataFrame and returns a Finding.

These back both the automatic battery and Claude's follow-up tools, so they
validate their inputs and raise AnalysisError with a message the model can act on.
Summaries and headlines are templated from the computed numbers.
"""

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

from app.schemas.findings import Effect, Finding, FindingChart, FindingKind, ValueFormat
from app.services.analysis import stats
from app.services.analysis.roles import resolve_column
from app.services.deck.resolve import format_number

ROWS = "__rows__"  # pseudo-metric: number of records
MAX_GROUPS = 12
MAX_DISCRETE_BINS = 8
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class AnalysisError(ValueError):
    """Bad analysis request (unknown column, wrong type, empty subset)."""


@dataclass(frozen=True)
class Where:
    column: str
    value: str


@dataclass
class Frame:
    """The analysis frame plus the facts every analysis needs about it."""

    df: pd.DataFrame
    binaries: frozenset[str]
    time: str | None
    sampled_from: int | None = None  # original row count when df is a sample

    @property
    def min_group(self) -> int:
        return max(20, round(0.01 * len(self.df)))


# ---------------------------------------------------------------- helpers


def _col(frame: Frame, name: str | None, what: str) -> str:
    resolved = resolve_column(frame.df, name)
    if resolved is None:
        raise AnalysisError(f"Unknown {what} column {name!r}. Use a name from the profile.")
    return resolved


def _subset(frame: Frame, where: Where | None) -> tuple[pd.DataFrame, str | None]:
    if where is None:
        return frame.df, None
    column = _col(frame, where.column, "filter")
    values = frame.df[column]
    mask = values.astype(str).str.casefold() == str(where.value).strip().casefold()
    if not mask.any():
        options = ", ".join(map(str, values.dropna().astype(str).value_counts().index[:8]))
        raise AnalysisError(f"No rows where {column} = {where.value!r}. Values include: {options}.")
    return frame.df[mask], f"{column} = {values[mask].iloc[0]}"


def _is_binary(frame: Frame, column: str) -> bool:
    return column in frame.binaries


def _as_binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    mapped = (
        series.astype(str)
        .str.strip()
        .str.casefold()
        .map(
            {
                "true": 1.0,
                "false": 0.0,
                "yes": 1.0,
                "no": 0.0,
                "1": 1.0,
                "0": 0.0,
                "1.0": 1.0,
                "0.0": 0.0,
                "y": 1.0,
                "n": 0.0,
            }
        )
    )
    return mapped.where(series.notna())


def _numeric(frame: Frame, column: str) -> pd.Series:
    series = frame.df[column]
    if _is_binary(frame, column):
        return _as_binary(series)
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() == 0:
        raise AnalysisError(f"{column!r} is not numeric.")
    return values


def _groups(series: pd.Series, min_n: int) -> pd.Series:
    """String labels with rare levels folded into 'Other' and missing as '(missing)'."""
    labels = series.map(lambda v: "(missing)" if pd.isna(v) else str(v))
    counts = labels.value_counts()
    keep = set(counts[counts >= min_n].index[:MAX_GROUPS])
    folded = labels.where(labels.isin(keep), "Other")
    if (folded == "Other").sum() < min_n:
        folded = folded.where(folded != "Other")
    return folded


def _fmt(value: float, fmt: ValueFormat) -> str:
    if fmt == "percent":
        return f"{value:.1f}%".replace(".0%", "%")
    if fmt == "correlation":
        return f"{value:.2f}"
    return format_number(value)


def _ratio_text(ratio: float) -> str:
    return f"{ratio:.1f}×"


def _pct_change(new: float, old: float) -> str:
    if old == 0:
        return "n/a"
    return f"{(new / old - 1) * 100:+.0f}%"


def _finding(
    *,
    kind: FindingKind,
    title: str,
    summary: str,
    headline: str,
    target: str,
    dimension: str | None,
    agg: str,
    result: stats.TestResult,
    n: int,
    chart: FindingChart,
    caveats: list[str],
    filter_desc: str | None,
    strength_override: stats.TestResult | None = None,
    facts: dict[str, str | float | list[str]] | None = None,
) -> Finding:
    """Build a Finding. `strength_override` lets a practical effect (e.g. a bin
    ratio) set the strength when it is larger than the test statistic's."""
    effect_source = result
    if strength_override is not None and stats.normalized(
        strength_override.effect_name, strength_override.effect
    ) > stats.normalized(result.effect_name, result.effect):
        effect_source = strength_override
    effect = Effect(
        name=effect_source.effect_name,
        value=round(effect_source.effect, 4),
        strength=effect_source.strength,
    )
    significant = (
        result.p_value is not None and result.p_value < 0.05 and effect.strength != "negligible"
    )
    if filter_desc:
        caveats = [*caveats, f"Computed on the subset where {filter_desc}."]
    return Finding(
        id="",
        kind=kind,
        title=title,
        summary=summary,
        headline=headline,
        target=target,
        dimension=dimension,
        agg=agg,
        effect=effect,
        p_value=None if result.p_value is None else float(f"{result.p_value:.3g}"),
        n=n,
        significant=significant,
        chart=chart,
        caveats=caveats,
        filter=filter_desc,
        facts=facts or {},
    )


def _metric_label(frame: Frame, metric: str) -> str:
    return "Record volume" if metric == ROWS else metric


def _month_span(months: list[int]) -> str:
    a, b = sorted(months)
    if b - a == 1:
        return f"{MONTHS[a - 1]}–{MONTHS[b - 1]}"
    if (a, b) == (1, 12):
        return "Dec–Jan"
    return f"{MONTHS[a - 1]} & {MONTHS[b - 1]}"


# ---------------------------------------------------------------- segments


def compare_segments(
    frame: Frame, metric: str, dimension: str, agg: str = "auto", where: Where | None = None
) -> Finding:
    metric = _col(frame, metric, "metric")
    dimension = _col(frame, dimension, "dimension")
    if metric == dimension:
        raise AnalysisError("The metric and the dimension must be different columns.")
    df, filter_desc = _subset(frame, where)
    binary = _is_binary(frame, metric)
    values = _numeric(Frame(df, frame.binaries, frame.time), metric)
    groups = _groups(df[dimension], frame.min_group)
    data = pd.DataFrame({"y": values, "g": groups}).dropna()
    if data["g"].nunique() < 2:
        raise AnalysisError(f"{dimension!r} has fewer than two groups with enough rows to compare.")

    caveats: list[str] = []
    if binary:
        fmt: ValueFormat = "percent"
        by = data.groupby("g")["y"].mean() * 100
        overall = data["y"].mean() * 100
        result = stats.binary_by_groups(data["y"], data["g"])
        agg_name = "rate"
    else:
        agg_name = "median" if agg == "median" else "mean"
        fmt = "number"
        by = data.groupby("g")["y"].agg(agg_name)
        overall = float(data["y"].agg(agg_name))
        result = stats.numeric_by_groups(data["y"], data["g"])
    counts = data.groupby("g").size()
    by = by.sort_values(ascending=False)
    top, bottom = by.index[0], by.index[-1]
    # For rates the standout is the highest-rate (risk) group; for averages, the group
    # furthest from the overall value in relative terms.
    standout = (
        top
        if binary
        else max(by.index, key=lambda g: abs(by[g] / overall - 1) if overall else abs(by[g]))
    )

    if binary:
        ratio = by[top] / by[bottom] if by[bottom] > 0 else math.inf
        headline = f"{_fmt(by[top], fmt)} vs {_fmt(by[bottom], fmt)}"
        summary = (
            f"{metric} rate is highest for {dimension} = {top} at {_fmt(by[top], fmt)} and lowest "
            f"for {bottom} at {_fmt(by[bottom], fmt)}, versus {_fmt(overall, fmt)} overall"
            + (f" ({_ratio_text(ratio)} gap)." if math.isfinite(ratio) else ".")
        )
    else:
        headline = _pct_change(by[standout], overall)
        summary = (
            f"Average {metric} is highest for {dimension} = {top} ({_fmt(by[top], fmt)}) "
            f"and lowest for {bottom} ({_fmt(by[bottom], fmt)}), "
            f"versus {_fmt(overall, fmt)} overall."
        )
        if agg_name == "median":
            summary = summary.replace("Average", "Median")
    small = [g for g, c in counts.items() if c < 50]
    if small:
        caveats.append(f"Small groups (under 50 rows): {', '.join(map(str, small[:4]))}.")
    return _finding(
        kind="segment",
        title=f"{metric} by {dimension}: {standout} stands out",
        summary=summary,
        headline=headline,
        target=metric,
        dimension=dimension,
        agg=agg_name,
        result=result,
        n=len(data),
        chart=FindingChart(
            kind="bars",
            categories=[str(g) for g in by.index],
            values=[round(float(v), 4) for v in by.to_numpy()],
            value_format=fmt,
            reference=round(float(overall), 4),
            reference_label="overall",
            counts=[int(counts[g]) for g in by.index],
        ),
        caveats=caveats,
        filter_desc=filter_desc,
        facts={
            "top": str(top),
            "bottom": str(bottom),
            "top_value": round(float(by[top]), 4),
            "bottom_value": round(float(by[bottom]), 4),
            "overall": round(float(overall), 4),
        },
    )


# ---------------------------------------------------------------- bins


def metric_by_bins(
    frame: Frame, metric: str, driver: str, bins: int = 4, where: Where | None = None
) -> Finding:
    metric = _col(frame, metric, "metric")
    driver = _col(frame, driver, "driver")
    if metric == driver:
        raise AnalysisError("The metric and the driver must be different columns.")
    if _is_binary(frame, driver):
        raise AnalysisError(f"{driver!r} is yes/no; use compare_segments for it instead.")
    bins = min(max(bins, 2), 10)
    df, filter_desc = _subset(frame, where)
    sub = Frame(df, frame.binaries, frame.time)
    y = _numeric(sub, metric)
    x = _numeric(sub, driver)
    data = pd.DataFrame({"y": y, "x": x}).dropna()
    if len(data) < frame.min_group * 2 or data["x"].nunique() < 2:
        raise AnalysisError(f"Not enough rows with both {metric} and {driver} to compare.")

    caveats: list[str] = []
    missing = int(x.isna().sum())
    if missing > 0.2 * len(x):
        caveats.append(f"{driver} is missing for {missing:,} rows, which are excluded.")

    min_bin = max(10, frame.min_group // 2)
    integer_valued = bool((data["x"] == data["x"].round()).all())
    if data["x"].nunique() <= MAX_DISCRETE_BINS or (integer_valued and data["x"].nunique() <= 25):
        # One band per value, with a sparse upper tail merged into "k+".
        counts_by_value = data["x"].value_counts().sort_index()
        cutoff = counts_by_value.index.max()
        tail = 0
        for value in sorted(counts_by_value.index, reverse=True):
            tail += counts_by_value[value]
            cutoff = value
            if tail >= min_bin:
                break
        # At most MAX_DISCRETE_BINS bands: fold everything above the 8th value into "k+".
        cutoff = (
            min(cutoff, sorted(counts_by_value.index)[MAX_DISCRETE_BINS - 1])
            if len(counts_by_value) > MAX_DISCRETE_BINS
            else cutoff
        )
        data["bin"] = data["x"].where(data["x"] < cutoff, cutoff)
        labels = {v: _fmt(v, "number") for v in sorted(data["bin"].unique())}
        if (data["x"] > cutoff).any():
            labels[cutoff] = f"{_fmt(cutoff, 'number')}+"
    else:
        codes = pd.qcut(data["x"], q=bins, labels=False, duplicates="drop")
        data["bin"] = codes
        labels = {
            code: f"{_fmt(group.min(), 'number')}–{_fmt(group.max(), 'number')}"
            for code, group in data.groupby("bin")["x"]
        }
    binary = _is_binary(frame, metric)
    fmt: ValueFormat = "percent" if binary else "number"
    per_bin = data.groupby("bin")["y"].mean() * (100 if binary else 1)
    counts = data.groupby("bin").size()
    # Drop thin bins (common with discrete drivers) so shapes aren't driven by a handful of rows.
    per_bin = per_bin[counts >= min_bin]
    if len(per_bin) < 2:
        raise AnalysisError(f"{driver!r} does not split into enough well-populated bands.")

    result = (
        stats.binary_vs_numeric(data["y"], data["x"])
        if binary
        else stats.numeric_vs_numeric(data["x"], data["y"])
    )
    first, last = float(per_bin.iloc[0]), float(per_bin.iloc[-1])
    shape = _shape(per_bin.to_numpy())
    lo, hi = float(per_bin.min()), float(per_bin.max())
    practical = stats.TestResult("rate ratio", hi / lo, result.p_value) if lo > 0 else None

    verb = {
        "increasing": "rises",
        "decreasing": "falls",
        "u_shape": "dips then rises",
        "inverted_u": "rises then falls",
    }.get(shape)
    if verb is None:
        verb = "is higher at high" if last > first else "is lower at high"
    reads = f"{verb} {driver}" if verb.startswith("is ") else f"{verb} across {driver}"
    first_label, last_label = labels[per_bin.index[0]], labels[per_bin.index[-1]]
    subject = f"{metric} rate" if binary else f"Average {metric}"
    summary = (
        f"{subject} {reads}: {_fmt(first, fmt)} at {driver} {first_label} "
        f"versus {_fmt(last, fmt)} at {driver} {last_label}."
    )
    if first > 0 and last > 0:
        headline = (
            _ratio_text(max(first, last) / min(first, last)) if binary else _pct_change(last, first)
        )
    else:
        headline = f"{_fmt(first, fmt)} → {_fmt(last, fmt)}"
    return _finding(
        kind="bins",
        title=f"{metric} {reads}",
        summary=summary,
        headline=headline,
        target=metric,
        dimension=driver,
        agg="rate" if binary else "mean",
        result=result,
        n=len(data),
        chart=FindingChart(
            kind="bars",
            categories=[labels[i] for i in per_bin.index],
            values=[round(float(v), 4) for v in per_bin.to_numpy()],
            value_format=fmt,
            reference=round(float(data["y"].mean() * (100 if binary else 1)), 4),
            reference_label="overall",
            counts=[int(counts[i]) for i in per_bin.index],
        ),
        caveats=caveats,
        filter_desc=filter_desc,
        strength_override=practical,
        facts={
            "first_band": first_label,
            "last_band": last_label,
            "first_value": round(first, 4),
            "last_value": round(last, 4),
            "shape": shape,
        },
    )


def _shape(values: np.ndarray) -> str:
    if len(values) < 3:
        return "increasing" if values[-1] > values[0] else "decreasing"
    rho = sps.spearmanr(np.arange(len(values)), values).statistic
    if rho >= 0.8:
        return "increasing"
    if rho <= -0.8:
        return "decreasing"
    interior = values[1:-1]
    if abs(rho) < 0.5 and interior.min() < 0.75 * min(values[0], values[-1]):
        return "u_shape"
    if abs(rho) < 0.5 and interior.max() > 1.3 * max(values[0], values[-1]):
        return "inverted_u"
    return "mixed"


# ---------------------------------------------------------------- trend


def trend(frame: Frame, metric: str, freq: str = "auto", where: Where | None = None) -> Finding:
    if frame.time is None:
        raise AnalysisError("The dataset has no date column, so trends can't be computed.")
    metric = metric if metric == ROWS else _col(frame, metric, "metric")
    df, filter_desc = _subset(frame, where)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        when = pd.to_datetime(df[frame.time], errors="coerce", format="mixed")
    binary = metric != ROWS and _is_binary(frame, metric)
    if metric == ROWS:
        y = pd.Series(1.0, index=df.index)
        agg = "count"
        fmt: ValueFormat = "number"
    else:
        y = _numeric(Frame(df, frame.binaries, frame.time), metric)
        nonneg = bool((y.dropna() >= 0).all())
        agg = "rate" if binary else ("sum" if nonneg and _is_additive(metric) else "mean")
        fmt = "percent" if binary else "number"
    data = pd.DataFrame({"t": when, "y": y}).dropna()
    if len(data) < 30:
        raise AnalysisError("Too few dated rows for a trend.")

    span = (data["t"].max() - data["t"].min()).days
    if freq == "auto":
        freq = "quarter" if span > 3 * 365 else "month" if span > 120 else "week"
    rule = {"week": "W-MON", "month": "MS", "quarter": "QS"}.get(freq)
    if rule is None:
        raise AnalysisError("freq must be week, month or quarter.")
    grouped = data.set_index("t")["y"].resample(rule)
    series = {
        "count": grouped.count(),
        "sum": grouped.sum(),
        "mean": grouped.mean(),
        "rate": grouped.mean() * 100,
    }[agg].dropna()
    # Drop a trailing partial period so the last point isn't artificially low.
    last_start = series.index[-1]
    period_end = last_start + pd.tseries.frequencies.to_offset(rule)
    if data["t"].max() < last_start + (period_end - last_start) * 0.6:
        series = series.iloc[:-1]
    if len(series) < 4:
        raise AnalysisError("Not enough periods for a trend; try a finer freq.")

    rho, p_trend = sps.spearmanr(np.arange(len(series)), series.to_numpy())
    trend_result = stats.TestResult("Spearman rho", float(rho), float(p_trend))
    k = max(1, min(3, len(series) // 4))
    start, end = float(series.iloc[:k].mean()), float(series.iloc[-k:].mean())

    seasonal: stats.TestResult | None = None
    peak_months: list[int] = []
    if freq == "month" and len(series) >= 24:
        by_month = series.groupby(pd.DatetimeIndex(series.index).month).mean()
        index = by_month / by_month.mean()
        peak_months = sorted(index.sort_values(ascending=False).index[:2].tolist())
        if agg in ("sum", "count"):
            observed = data.groupby(data["t"].dt.month).size().reindex(range(1, 13), fill_value=0)
            _, p_season = sps.chisquare(observed.to_numpy())
        else:
            month_groups = [g.to_numpy() for _, g in data.groupby(data["t"].dt.month)["y"]]
            _, p_season = sps.kruskal(*month_groups)
        seasonal = stats.TestResult(
            "seasonal ratio", float(index.max() / index.min()), float(p_season)
        )

    label = _metric_label(frame, metric)
    change = _pct_change(end, start)
    period = {"week": "week", "month": "month", "quarter": "quarter"}[freq]
    trend_text = (
        f"{label} {'rose' if end > start else 'fell'} {change} from the first to the last {period}s"
        if trend_result.strength != "negligible" and p_trend < 0.05
        else f"{label} shows no clear long-run trend ({change} first to last {period}s)"
    )
    use_season = seasonal is not None and stats.normalized(
        "seasonal ratio", seasonal.effect
    ) >= stats.normalized("Spearman rho", trend_result.effect)
    if use_season and seasonal is not None:
        peak_names = _month_span(peak_months)
        by_month_index = series.groupby(pd.DatetimeIndex(series.index).month).mean()
        peak_ratio = float(by_month_index[peak_months].mean() / by_month_index.mean())
        summary = (
            f"{label} is seasonal: {peak_names} run at {_ratio_text(peak_ratio)} "
            f"the average month. {trend_text}."
        )
        title = f"{label} peaks in {peak_names}"
        headline = f"{_ratio_text(peak_ratio)} in {peak_names}"
        result = seasonal
    else:
        summary = f"{trend_text}, averaging {_fmt(float(series.mean()), fmt)} per {period}."
        title = f"{label} trend over time"
        headline = change
        result = trend_result
    caveats = ["Seasonality is estimated from only two years of data."] if use_season else []
    finding = _finding(
        kind="trend",
        title=title,
        summary=summary,
        headline=headline,
        target=label,
        dimension=frame.time,
        agg=agg,
        result=result,
        n=len(data),
        chart=FindingChart(
            kind="line",
            categories=[_period_label(ts, freq) for ts in series.index],
            values=[round(float(v), 4) for v in series.to_numpy()],
            value_format=fmt,
            reference=round(float(series.mean()), 4),
            reference_label=f"average {period}",
        ),
        caveats=caveats,
        filter_desc=filter_desc,
        facts={
            "change": change,
            "start_value": round(start, 4),
            "end_value": round(end, 4),
            "peak_months": [MONTHS[m - 1] for m in peak_months],
        },
    )
    return finding


def _is_additive(metric: str) -> bool:
    name = metric.lower()
    return any(
        k in name
        for k in (
            "revenue",
            "sales",
            "amount",
            "spend",
            "charge",
            "cost",
            "margin",
            "profit",
            "units",
            "quantity",
            "count",
            "total",
        )
    )


def _period_label(ts: pd.Timestamp, freq: str) -> str:
    if freq == "quarter":
        return f"{ts.year} Q{(ts.month - 1) // 3 + 1}"
    if freq == "month":
        return ts.strftime("%Y-%m")
    return ts.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- concentration


def concentration(frame: Frame, metric: str, entity: str) -> Finding:
    metric = _col(frame, metric, "metric")
    entity = _col(frame, entity, "entity")
    data = pd.DataFrame({"y": _numeric(frame, metric), "e": frame.df[entity]}).dropna()
    if (data["y"] < 0).any():
        raise AnalysisError(
            f"{metric!r} has negative values; concentration needs a non-negative measure."
        )
    totals = data.groupby("e")["y"].sum().sort_values(ascending=False)
    if len(totals) < 10 or totals.sum() <= 0:
        raise AnalysisError(f"Too few {entity} values to measure concentration.")
    grand = float(totals.sum())

    def share(fraction: float) -> float:
        return float(totals.iloc[: max(1, math.ceil(len(totals) * fraction))].sum() / grand)

    s10, s20, s50 = share(0.1), share(0.2), share(0.5)
    sorted_asc = np.sort(totals.to_numpy())
    cum = np.cumsum(sorted_asc)
    gini = float(1 - 2 * np.sum(cum / cum[-1]) / len(cum) + 1 / len(cum))
    result = stats.TestResult("top-20% share", s20, None)
    finding = _finding(
        kind="concentration",
        title=f"A few {entity} values drive most of {metric}",
        summary=(
            f"The top 10% of {entity} "
            f"({max(1, math.ceil(len(totals) * 0.1)):,} of {len(totals):,}) "
            f"account for {s10 * 100:.0f}% of {metric}; "
            f"the top 20% for {s20 * 100:.0f}% (Gini {gini:.2f})."
        ),
        headline=f"{s10 * 100:.0f}%",
        target=metric,
        dimension=entity,
        agg="sum",
        result=result,
        n=len(data),
        chart=FindingChart(
            kind="bars",
            categories=["Top 10%", "Top 20%", "Top 50%"],
            values=[round(s10 * 100, 2), round(s20 * 100, 2), round(s50 * 100, 2)],
            value_format="percent",
        ),
        caveats=[],
        filter_desc=None,
        facts={"top10_share": round(s10, 4), "top20_share": round(s20, 4), "gini": round(gini, 4)},
    )
    # Descriptive, not a test: significant means practically concentrated.
    finding.significant = result.strength in ("moderate", "strong")
    return finding


# ---------------------------------------------------------------- crosstab


def crosstab(
    frame: Frame, dimension_a: str, dimension_b: str, where: Where | None = None
) -> Finding:
    a = _col(frame, dimension_a, "dimension")
    b = _col(frame, dimension_b, "dimension")
    if a == b:
        raise AnalysisError("Pick two different columns.")
    df, filter_desc = _subset(frame, where)
    ga, gb = _groups(df[a], frame.min_group), _groups(df[b], frame.min_group)
    data = pd.DataFrame({"a": ga, "b": gb}).dropna()
    result = stats.categorical_vs_categorical(data["a"], data["b"])
    table = pd.crosstab(data["a"], data["b"], normalize="index") * 100
    # Report the share of b's most over-represented level within each a group.
    overall = data["b"].value_counts(normalize=True) * 100
    lift = table.div(overall, axis=1)
    level = str(lift.max(axis=0).idxmax())
    column = table[level].sort_values(ascending=False)
    top = column.index[0]
    return _finding(
        kind="crosstab",
        title=f"{a} and {b} are linked",
        summary=(
            f"{b} = {level} makes up {column.iloc[0]:.0f}% of {a} = {top}, versus "
            f"{overall[level]:.0f}% overall (Cramér's V {result.effect:.2f})."
        ),
        headline=_ratio_text(column.iloc[0] / overall[level]),
        target=b,
        dimension=a,
        agg="share",
        result=result,
        n=len(data),
        chart=FindingChart(
            kind="bars",
            categories=[str(g) for g in column.index],
            values=[round(float(v), 4) for v in column.to_numpy()],
            value_format="percent",
            reference=round(float(overall[level]), 4),
            reference_label=f"{b} = {level} overall",
        ),
        caveats=[],
        filter_desc=filter_desc,
    )


# ---------------------------------------------------------------- drivers


@dataclass(frozen=True)
class DriverTest:
    column: str
    kind: str  # "dimension" | "measure"
    result: stats.TestResult


LEAKAGE_ASSOCIATION = 0.85


def components_of(frame: Frame, target: str, measures: list[str]) -> list[str]:
    """Measures the target is (almost exactly) computed from: a±b, a×b or a restatement."""
    if _is_binary(frame, target):
        return []
    y = pd.to_numeric(frame.df[target], errors="coerce")
    cols = {m: pd.to_numeric(frame.df[m], errors="coerce") for m in measures if m != target}
    found: set[str] = set()

    def close(candidate: pd.Series) -> bool:
        pair = pd.concat([y, candidate], axis=1).dropna()
        if len(pair) < 10 or pair.iloc[:, 1].std() == 0 or pair.iloc[:, 0].std() == 0:
            return False
        return abs(float(np.corrcoef(pair.iloc[:, 0], pair.iloc[:, 1])[0, 1])) >= 0.995

    names = list(cols)
    for m in names:
        if close(cols[m]):
            found.add(m)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if close(cols[a] - cols[b]) or close(cols[a] + cols[b]) or close(cols[a] * cols[b]):
                found.update((a, b))
    return sorted(found)


def driver_tests(
    frame: Frame,
    target: str,
    dimensions: list[str],
    measures: list[str],
    exclude: frozenset[str] = frozenset(),
) -> tuple[list[DriverTest], list[str]]:
    """Association of every candidate column with the target, strongest first.

    Near-perfect associations are returned separately: they are almost always
    components or restatements of the target (margin = revenue - cost).
    """
    target = _col(frame, target, "target")
    binary = _is_binary(frame, target)
    y = _numeric(frame, target)
    components = set(components_of(frame, target, measures))
    skip = {target, *exclude, *components}
    tests: list[DriverTest] = []
    for dim in dimensions:
        if dim in skip:
            continue
        groups = _groups(frame.df[dim], frame.min_group)
        data = pd.DataFrame({"y": y, "g": groups}).dropna()
        if data["g"].nunique() < 2:
            continue
        result = (
            stats.binary_by_groups(data["y"], data["g"])
            if binary
            else stats.numeric_by_groups(data["y"], data["g"])
        )
        if result.effect_name == "rate ratio":
            # Put rate ratios on the common scale via Cramér's V for ranking.
            v = stats.categorical_vs_categorical(data["g"], data["y"])
            result = stats.TestResult("Cramer's V", v.effect, result.p_value)
        tests.append(DriverTest(dim, "dimension", result))
    for measure in measures:
        if measure in skip:
            continue
        x = _numeric(frame, measure)
        result = stats.binary_vs_numeric(y, x) if binary else stats.numeric_vs_numeric(x, y)
        tests.append(DriverTest(measure, "measure", result))
    leaks = sorted(
        components | {t.column for t in tests if t.result.association >= LEAKAGE_ASSOCIATION}
    )
    kept = [t for t in tests if t.column not in leaks]
    kept.sort(key=lambda t: t.result.association, reverse=True)
    return kept, leaks


def driver_ranking(
    frame: Frame,
    target: str,
    dimensions: list[str],
    measures: list[str],
    exclude: frozenset[str] = frozenset(),
) -> Finding:
    target = _col(frame, target, "target")
    tests, leaks = driver_tests(frame, target, dimensions, measures, exclude)
    significant = [t for t in tests if t.result.p_value is not None and t.result.p_value < 0.05]
    top = (significant or tests)[:8]
    if len(top) < 2:
        raise AnalysisError(f"Too few candidate drivers to rank against {target!r}.")
    best = top[0]
    names = ", ".join(t.column for t in top[:3])
    caveats = ["Associations, not causes: drivers can be correlated with each other."]
    if leaks:
        caveats.append(
            f"Excluded as likely components or restatements of {target}: {', '.join(leaks)}."
        )
    return _finding(
        kind="drivers",
        title=f"What moves with {target}",
        summary=(
            f"Of {len(tests)} columns tested, {len(significant)} are significantly associated with "
            f"{target}; the strongest are {names}."
        ),
        headline=best.column,
        target=target,
        dimension=None,
        agg="association",
        result=best.result,
        n=len(frame.df),
        chart=FindingChart(
            kind="ranking",
            categories=[t.column for t in top],
            values=[round(t.result.association, 4) for t in top],
            value_format="correlation",
        ),
        caveats=caveats,
        filter_desc=None,
    )
