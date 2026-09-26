"""Deterministic exploratory data analysis: DataFrame -> DatasetProfile.

Everything here is pure and seeded, so the same input always yields the same profile.
All floats pass through `_f`, so the output never contains NaN or inf.
"""

import math
import re
import warnings
from typing import Any

import pandas as pd

from app.schemas.profile import (
    ColumnProfile,
    CorrelationMatrix,
    CorrelationPair,
    DatasetProfile,
    InferredType,
    TopValue,
)

MAX_PROFILE_COLUMNS = 200
MAX_CORRELATION_COLUMNS = 15
MAX_TOP_CORRELATIONS = 20
TOP_CORRELATION_THRESHOLD = 0.5
TOP_VALUES_LIMIT = 10
HIGH_MISSING_PCT = 50.0
HIGH_CARDINALITY = 50
TEXT_AVG_LENGTH = 50
ID_MIN_ROWS = 20
DATETIME_PARSE_RATIO = 0.9
_DATETIME_PROBE_ROWS = 1000
_BOOL_STRINGS = frozenset({"true", "false", "yes", "no", "y", "n", "t", "f"})
_ID_NAME = re.compile(r"(^|[_\s-])id$|^id[_\s-]|_key$", re.IGNORECASE)


def build_profile(df: pd.DataFrame, sample_rows: int) -> DatasetProfile:
    warnings_out: list[str] = []
    n_rows_total = len(df)
    memory_bytes = int(df.memory_usage(deep=True).sum())

    sampled = n_rows_total > sample_rows
    if sampled:
        df = df.sample(n=sample_rows, random_state=0).sort_index()
        warnings_out.append(
            f"Statistics were computed on a random sample of {sample_rows:,} "
            f"of {n_rows_total:,} rows."
        )

    if len(df.columns) > MAX_PROFILE_COLUMNS:
        warnings_out.append(
            f"Only the first {MAX_PROFILE_COLUMNS} of {len(df.columns)} columns were profiled."
        )
        df = df.iloc[:, :MAX_PROFILE_COLUMNS]

    columns: list[ColumnProfile] = []
    numeric_frame: dict[str, pd.Series] = {}
    for name in df.columns:
        col, numeric = _profile_column(str(name), df[name])
        columns.append(col)
        if numeric is not None:
            numeric_frame[col.name] = numeric
        warnings_out.extend(_column_warnings(col, len(df)))

    missing_total = int(df.isna().sum().sum())
    cells = df.size
    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        warnings_out.append(f"{duplicate_rows:,} fully duplicated rows.")

    correlation, top_pairs = _correlations(columns, numeric_frame)

    return DatasetProfile(
        n_rows=n_rows_total,
        n_cols=len(df.columns),
        memory_bytes=memory_bytes,
        duplicate_rows=duplicate_rows,
        missing_cells_total=missing_total,
        missing_pct_total=_pct(missing_total, cells),
        sampled=sampled,
        sample_rows=sample_rows if sampled else None,
        columns=columns,
        correlation=correlation,
        top_correlations=top_pairs,
        warnings=warnings_out,
    )


def _profile_column(name: str, s: pd.Series) -> tuple[ColumnProfile, pd.Series | None]:
    """Profile one column. Also returns the float series if the column is numeric."""
    non_null = s.dropna()
    base: dict[str, Any] = {
        "name": name,
        "dtype": str(s.dtype),
        "missing_count": int(s.isna().sum()),
        "missing_pct": _pct(int(s.isna().sum()), len(s)),
        "unique_count": int(non_null.nunique()),
    }
    kind, parsed = _infer_type(name, s, non_null)
    base["inferred_type"] = kind

    if kind == "numeric":
        values = pd.to_numeric(s, errors="coerce").astype(float)
        infinite = values.isin([math.inf, -math.inf])
        if infinite.any():
            base["infinite_count"] = int(infinite.sum())
            values = values.mask(infinite)
        base.update(_numeric_stats(values.dropna()))
        return ColumnProfile(**base), values
    if kind in ("categorical", "boolean"):
        counts = non_null.astype(str).value_counts().head(TOP_VALUES_LIMIT)
        base["top_values"] = [TopValue(value=str(k), count=int(v)) for k, v in counts.items()]
    elif kind == "datetime" and parsed is not None:
        dates = parsed.dropna()
        if not dates.empty:
            base["min_date"] = dates.min().isoformat()
            base["max_date"] = dates.max().isoformat()
    return ColumnProfile(**base), None


def _infer_type(
    name: str, s: pd.Series, non_null: pd.Series
) -> tuple[InferredType, pd.Series | None]:
    if pd.api.types.is_bool_dtype(s):
        return "boolean", None
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", s
    if pd.api.types.is_numeric_dtype(s):
        if _looks_like_id(name, s, non_null) and pd.api.types.is_integer_dtype(non_null):
            return "id", None
        return "numeric", None
    if isinstance(s.dtype, pd.CategoricalDtype):
        return "categorical", None

    if non_null.empty:
        return "categorical", None
    as_str = non_null.astype(str)
    if set(as_str.str.strip().str.lower().unique()) <= _BOOL_STRINGS:
        return "boolean", None
    parsed = _try_parse_datetime(as_str)
    if parsed is not None:
        return "datetime", parsed
    if _looks_like_id(name, s, non_null) and as_str.str.len().mean() <= TEXT_AVG_LENGTH:
        return "id", None
    if as_str.str.len().mean() > TEXT_AVG_LENGTH:
        return "text", None
    return "categorical", None


def _looks_like_id(name: str, s: pd.Series, non_null: pd.Series) -> bool:
    all_unique = len(non_null) >= ID_MIN_ROWS and non_null.nunique() == len(non_null)
    if pd.api.types.is_numeric_dtype(s):
        return all_unique and bool(_ID_NAME.search(name))
    return all_unique


def _try_parse_datetime(values: pd.Series) -> pd.Series | None:
    # Cheap rejection first: date strings contain digits.
    if values.str.contains(r"\d", regex=True).mean() < DATETIME_PARSE_RATIO:
        return None
    probe = values.head(_DATETIME_PROBE_ROWS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for fmt in ("ISO8601", "mixed"):
            try:
                if pd.to_datetime(probe, errors="coerce", format=fmt).notna().mean() >= (
                    DATETIME_PARSE_RATIO
                ):
                    return pd.to_datetime(values, errors="coerce", format=fmt)
            except (ValueError, TypeError, OverflowError):
                continue
    return None


def _numeric_stats(v: pd.Series) -> dict[str, Any]:
    if v.empty:
        return {}
    q1, median, q3 = (float(x) for x in v.quantile([0.25, 0.5, 0.75]))
    iqr = q3 - q1
    outliers = int(((v < q1 - 1.5 * iqr) | (v > q3 + 1.5 * iqr)).sum())
    return {
        "mean": _f(v.mean()),
        "std": _f(v.std()),
        "min": _f(v.min()),
        "p25": _f(q1),
        "median": _f(median),
        "p75": _f(q3),
        "max": _f(v.max()),
        "skew": _f(v.skew()),
        "outlier_count": outliers,
    }


def _column_warnings(col: ColumnProfile, n_rows: int) -> list[str]:
    out: list[str] = []
    if col.infinite_count:
        out.append(
            f"'{col.name}' has {col.infinite_count:,} infinite values (excluded from stats)."
        )
    if col.missing_pct > HIGH_MISSING_PCT:
        out.append(f"'{col.name}' is {col.missing_pct:.1f}% missing.")
    if col.unique_count <= 1 and n_rows > 1:
        out.append(f"'{col.name}' is constant and carries no information.")
    if col.inferred_type == "categorical" and col.unique_count > HIGH_CARDINALITY:
        out.append(f"'{col.name}' is high-cardinality ({col.unique_count:,} distinct values).")
    return out


def _correlations(
    columns: list[ColumnProfile], numeric: dict[str, pd.Series]
) -> tuple[CorrelationMatrix | None, list[CorrelationPair]]:
    candidates = sorted(
        (c for c in columns if c.name in numeric and c.unique_count > 1),
        key=lambda c: c.missing_count,
    )[:MAX_CORRELATION_COLUMNS]
    if len(candidates) < 2:
        return None, []

    names = [c.name for c in candidates]
    corr = pd.DataFrame({n: numeric[n] for n in names}).corr(method="pearson", min_periods=3)
    matrix = [[_f(corr.at[a, b], 4) for b in names] for a in names]

    pairs: list[CorrelationPair] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = _f(corr.at[a, b], 4)
            if r is not None and abs(r) >= TOP_CORRELATION_THRESHOLD:
                pairs.append(CorrelationPair(a=a, b=b, r=r))
    pairs.sort(key=lambda p: (-abs(p.r), p.a, p.b))
    return CorrelationMatrix(columns=names, matrix=matrix), pairs[:MAX_TOP_CORRELATIONS]


def _f(x: Any, digits: int = 6) -> float | None:
    if x is None:
        return None
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return round(value, digits) if math.isfinite(value) else None


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0
