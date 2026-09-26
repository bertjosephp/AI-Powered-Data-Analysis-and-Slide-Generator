"""Which columns are outcomes, drivers, time and entities.

Uses the profiler's inferred types plus column-name heuristics. A target
chosen by the user always wins; otherwise the most outcome-like columns are
picked (binary business outcomes first, then value measures).
"""

import re

import pandas as pd

from app.schemas.findings import ColumnRoles
from app.schemas.profile import DatasetProfile

MAX_DIMENSION_LEVELS = 30
MAX_TARGETS = 2

_BINARY_OUTCOME = re.compile(
    r"churn|attrition|left|leav|readmit|return|convert|default|fraud|cancel|won|success|"
    r"respond|click|purchas|renew|retain|fail|complain|late|delay",
    re.IGNORECASE,
)
_PROFIT = re.compile(r"profit|margin|ltv|lifetime", re.IGNORECASE)
_VALUE = re.compile(
    r"revenue|sales|amount|spend|charge|price|value|income|gmv|total", re.IGNORECASE
)
# Preferred order when picking the measure to test for concentration (who brings the value).
_VALUE_PRIORITY = [
    "revenue",
    "sales",
    "gmv",
    "amount",
    "spend",
    "charge",
    "income",
    "total",
    "value",
]
_OUTCOME_NUMERIC = re.compile(r"score|rating|satisfaction|nps|duration|days|time", re.IGNORECASE)
_ENTITY = re.compile(
    r"customer|client|user|account|patient|member|employee|store|seller|vendor|supplier",
    re.IGNORECASE,
)
_NOT_A_TARGET = re.compile(
    r"(^|_)(id|key|code|zip|postal|phone|year|month|week|day_of)", re.IGNORECASE
)


def infer_roles(
    df: pd.DataFrame, profile: DatasetProfile, target: str | None = None
) -> ColumnRoles:
    n_rows = len(df)
    time = next((c.name for c in profile.columns if c.inferred_type == "datetime"), None)
    numeric = [
        c.name for c in profile.columns if c.inferred_type == "numeric" and c.unique_count > 1
    ]
    # 0/1 integer columns are binary outcomes, not measures.
    zero_one = [m for m in numeric if set(df[m].dropna().unique()) <= {0, 1}]
    measures = [m for m in numeric if m not in zero_one]
    binaries = [
        c.name for c in profile.columns if c.inferred_type == "boolean" and c.unique_count == 2
    ] + zero_one
    dimensions = [
        c.name
        for c in profile.columns
        if c.inferred_type in ("categorical", "boolean")
        and 2 <= c.unique_count <= MAX_DIMENSION_LEVELS
    ]
    entity = next(
        (
            c.name
            for c in profile.columns
            if _ENTITY.search(c.name)
            and c.inferred_type in ("categorical", "id")
            and 10 < c.unique_count < 0.9 * n_rows
        ),
        None,
    )
    value_measure = next(
        (
            m
            for key in _VALUE_PRIORITY
            for m in measures
            if key in m.lower() and "unit" not in m.lower() and (df[m].dropna() >= 0).all()
        ),
        None,
    )

    targets: list[str] = []
    if target:
        targets.append(target)
    for candidate, score in _rank_targets(measures, binaries):
        # Generic columns (e.g. an unnamed yes/no flag) only become a target if nothing
        # more outcome-like exists.
        if score < 1.0 and targets:
            break
        if candidate not in targets and len(targets) < MAX_TARGETS:
            targets.append(candidate)

    return ColumnRoles(
        time=time,
        measures=measures,
        dimensions=dimensions,
        binaries=binaries,
        entity=entity,
        value_measure=value_measure,
        targets=targets,
    )


def _rank_targets(measures: list[str], binaries: list[str]) -> list[tuple[str, float]]:
    scored: list[tuple[float, int, str]] = []
    for i, name in enumerate([*binaries, *measures]):
        if _NOT_A_TARGET.search(name):
            continue
        is_binary = name in binaries
        if is_binary and _BINARY_OUTCOME.search(name):
            score = 3.0
        elif _PROFIT.search(name):
            score = 2.5
        elif _VALUE.search(name) and not name.lower().startswith("unit"):
            score = 2.0
        elif not is_binary and _OUTCOME_NUMERIC.search(name):
            score = 1.0
        elif is_binary:
            score = 0.8
        else:
            continue
        scored.append((-score, i, name))
    return [(name, -neg) for neg, _, name in sorted(scored)]


def resolve_column(df: pd.DataFrame, name: str | None) -> str | None:
    """Exact, then case-insensitive column match."""
    if not name:
        return None
    if name in df.columns:
        return name
    folded = name.strip().casefold()
    return next((c for c in df.columns if str(c).casefold() == folded), None)
