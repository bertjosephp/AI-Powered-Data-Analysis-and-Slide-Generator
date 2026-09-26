"""SlideSpec + DatasetProfile -> ResolvedSlide.

Every number that reaches a slide comes from here, computed from the profile.
References Claude got wrong (unknown column, metric that doesn't apply) degrade:
a KPI is dropped, a chart slide renders as text only. A deck is always produced.
"""

import logging
from datetime import date

from app.schemas.deck import (
    ChartInsightSlide,
    ChartRef,
    KpiSlide,
    MetricRef,
    ResolvedChart,
    ResolvedChartInsightSlide,
    ResolvedKpi,
    ResolvedKpiSlide,
    ResolvedSlide,
    ResolvedTitleSlide,
    SlideSpec,
    TitleSlide,
)
from app.schemas.findings import Finding
from app.schemas.profile import ColumnProfile, DatasetProfile

log = logging.getLogger(__name__)

MAX_CHART_BARS = 8
MAX_CORRELATION_BARS = 6
_NUMERIC_STATS = {"mean", "median", "min", "max", "std"}


def resolve_slides(
    slides: list[SlideSpec],
    profile: DatasetProfile,
    dataset_name: str,
    today: date | None = None,
    findings: list[Finding] | None = None,
) -> list[ResolvedSlide]:
    by_id = {f.id: f for f in findings or []}
    resolved: list[ResolvedSlide] = []
    for slide in slides:
        if isinstance(slide, TitleSlide):
            resolved.append(
                ResolvedTitleSlide(
                    layout="title",
                    title=slide.title,
                    subtitle=slide.subtitle,
                    meta=_title_meta(profile, dataset_name, today or date.today()),
                )
            )
        elif isinstance(slide, KpiSlide):
            kpis = [
                k
                for k in (_resolve_kpi(k.label, k.metric, profile, by_id) for k in slide.kpis)
                if k
            ]
            resolved.append(ResolvedKpiSlide(title=slide.title, kpis=kpis))
        elif isinstance(slide, ChartInsightSlide):
            resolved.append(
                ResolvedChartInsightSlide(
                    title=slide.title,
                    bullets=slide.bullets,
                    chart=resolve_chart(slide.chart, profile, by_id),
                )
            )
        else:
            resolved.append(slide)
    return resolved


def _title_meta(profile: DatasetProfile, dataset_name: str, today: date) -> str:
    return (
        f"{dataset_name} · {format_number(profile.n_rows)} rows × {profile.n_cols} columns · "
        f"{today.strftime('%B %Y')}"
    )


# ---------- metrics ----------


def _resolve_kpi(
    label: str, ref: MetricRef, profile: DatasetProfile, findings: dict[str, Finding]
) -> ResolvedKpi | None:
    result = resolve_metric(ref, profile, findings)
    if result is None:
        log.warning("Dropping KPI %r: cannot resolve %s", label, ref.model_dump())
        return None
    value, caption = result
    return ResolvedKpi(label=label, value=value, caption=caption)


def resolve_metric(
    ref: MetricRef, profile: DatasetProfile, findings: dict[str, Finding] | None = None
) -> tuple[str, str] | None:
    """Returns (formatted value, caption naming its source), or None if not resolvable."""
    if ref.metric == "finding":
        finding = (findings or {}).get(ref.finding_id or "")
        return (finding.headline, finding_caption(finding)) if finding else None
    match ref.metric:
        case "rows":
            return format_number(profile.n_rows), "rows in the dataset"
        case "columns":
            return str(profile.n_cols), "columns profiled"
        case "missing_cells_pct":
            return format_percent(profile.missing_pct_total), "of all cells are missing"
        case "duplicate_rows":
            return format_number(profile.duplicate_rows), "fully duplicated rows"

    col = find_column(profile, ref.column)
    if col is None:
        return None
    if ref.metric in _NUMERIC_STATS:
        value = getattr(col, ref.metric)
        if col.inferred_type != "numeric" or value is None:
            return None
        return format_number(value), f"{ref.metric} of {col.name}"
    if ref.metric == "unique_count":
        return format_number(col.unique_count), f"distinct values of {col.name}"
    if ref.metric == "missing_pct":
        return format_percent(col.missing_pct), f"of {col.name} is missing"
    if ref.metric == "top_value_share" and col.top_values:
        top = col.top_values[0]
        base = _non_missing_rows(profile, col)
        if base == 0:
            return None
        return format_percent(100 * top.count / base), f"of {col.name} is {top.value}"
    return None


# ---------- charts ----------


def resolve_chart(
    ref: ChartRef, profile: DatasetProfile, findings: dict[str, Finding] | None = None
) -> ResolvedChart | None:
    if ref.chart == "finding":
        finding = (findings or {}).get(ref.finding_id or "")
        chart = finding_chart(finding) if finding else None
    else:
        chart = _build_chart(ref, profile)
    if chart is None:
        log.warning("Chart %s could not be resolved; rendering text only", ref.model_dump())
    return chart


def _build_chart(ref: ChartRef, profile: DatasetProfile) -> ResolvedChart | None:
    if ref.chart == "correlations":
        pairs = profile.top_correlations[:MAX_CORRELATION_BARS]
        if not pairs:
            return None
        return ResolvedChart(
            kind="correlations",
            caption="Strongest correlations (Pearson r)",
            categories=[f"{p.a} × {p.b}" for p in pairs],
            values=[p.r for p in pairs],
            value_format="correlation",
        )

    if ref.chart == "missing_values":
        cols = sorted(
            (c for c in profile.columns if c.missing_count > 0), key=lambda c: -c.missing_pct
        )[:MAX_CHART_BARS]
        if not cols:
            return None
        return ResolvedChart(
            kind="missing_values",
            caption="Share of values missing, by column",
            categories=[c.name for c in cols],
            values=[c.missing_pct for c in cols],
            value_format="percent",
        )

    col = find_column(profile, ref.column)
    if col is None:
        return None

    if ref.chart == "top_values" and col.top_values:
        top = col.top_values[:MAX_CHART_BARS]
        return ResolvedChart(
            kind="top_values",
            caption=f"Most common values of {col.name} (count)",
            categories=[t.value for t in top],
            values=[float(t.count) for t in top],
            value_format="number",
        )

    if ref.chart == "numeric_summary" and col.inferred_type == "numeric":
        stats = [
            ("Min", col.min),
            ("P25", col.p25),
            ("Median", col.median),
            ("P75", col.p75),
            ("Max", col.max),
        ]
        if any(v is None for _, v in stats):
            return None
        return ResolvedChart(
            kind="numeric_summary",
            caption=f"Distribution of {col.name}",
            categories=[name for name, _ in stats],
            values=[float(v) for _, v in stats if v is not None],
            value_format="number",
        )
    return None


def finding_chart(finding: Finding) -> ResolvedChart:
    src = finding.chart
    style = {"line": "line", "ranking": "bars"}.get(src.kind, "bars")
    if finding.kind in ("bins", "concentration"):
        style = "columns"  # ordered bands read left to right
    fmt = "number" if src.value_format == "currency" else src.value_format
    return ResolvedChart(
        kind="finding",
        caption=finding.title,
        categories=src.categories,
        values=src.values,
        value_format=fmt,
        style=style,
        reference=src.reference,
        reference_label=src.reference_label,
        finding_id=finding.id,
    )


def finding_caption(f: Finding) -> str:
    """A short caption for a KPI card showing a finding's headline."""
    facts = f.facts
    if f.kind == "segment":
        if f.agg == "rate":
            return f"{f.target} rate, {f.dimension} = {facts.get('top')} vs {facts.get('bottom')}"
        return f"{f.target} for {f.dimension} = {facts.get('top')} vs overall"
    if f.kind == "bins":
        return f"{f.target}, {f.dimension} {facts.get('last_band')} vs {facts.get('first_band')}"
    if f.kind == "trend":
        return f"{f.target}: seasonal peak" if facts.get("peak_months") else f"{f.target} change"
    if f.kind == "concentration":
        return f"of {f.target} from the top 10% of {f.dimension}"
    if f.kind == "drivers":
        return f"strongest driver of {f.target}"
    return f.title


# ---------- helpers ----------


def find_column(profile: DatasetProfile, name: str | None) -> ColumnProfile | None:
    if not name:
        return None
    exact = next((c for c in profile.columns if c.name == name), None)
    if exact:
        return exact
    folded = name.strip().casefold()
    return next((c for c in profile.columns if c.name.casefold() == folded), None)


def _non_missing_rows(profile: DatasetProfile, col: ColumnProfile) -> int:
    base = profile.sample_rows if profile.sampled and profile.sample_rows else profile.n_rows
    return base - col.missing_count


def format_number(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if magnitude >= 10_000:
        return f"{value / 1_000:.1f}K"
    if float(value).is_integer():
        return f"{int(value):,}"
    if magnitude >= 100:
        return f"{value:,.0f}"
    if magnitude >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:.3g}"


def format_percent(value: float) -> str:
    return f"{value:.1f}%".replace(".0%", "%")
