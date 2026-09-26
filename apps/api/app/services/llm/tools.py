"""Follow-up analysis tools Claude can call, and their executor.

Each tool runs one of the analysis functions against the server-side dataset
and returns a new Finding (as JSON) with a fresh id. Rows never leave the
backend: tools only return aggregates.
"""

import json
from typing import Any

from anthropic.types import ToolParam

from app.schemas.findings import ColumnRoles, Finding
from app.services.analysis.analyses import (
    ROWS,
    AnalysisError,
    Frame,
    Where,
    compare_segments,
    crosstab,
    driver_ranking,
    metric_by_bins,
    trend,
)

_WHERE: dict[str, Any] = {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "column": {"type": "string", "description": "Column to filter on."},
                "value": {
                    "type": "string",
                    "description": "Keep rows where the column equals this value.",
                },
            },
            "required": ["column", "value"],
            "additionalProperties": False,
        },
        {"type": "null"},
    ],
    "description": "Optional single-condition filter to drill into a subset "
    "(e.g. plan = Enterprise).",
}


def _tool(name: str, description: str, properties: dict[str, Any]) -> ToolParam:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS: list[ToolParam] = [
    _tool(
        "compare_segments",
        "Compare a metric across the groups of a categorical or yes/no column. For a yes/no "
        "metric this compares rates; otherwise averages. Returns group values, the overall "
        "value, an effect size and a p-value.",
        {
            "metric": {"type": "string", "description": "Numeric or yes/no column to compare."},
            "dimension": {
                "type": "string",
                "description": "Categorical or yes/no column to group by.",
            },
            "where": _WHERE,
        },
    ),
    _tool(
        "metric_by_bins",
        "Show how a metric changes across bands of a numeric driver (quartiles, or one band per "
        "value for small integers). Use it to find thresholds and non-linear patterns.",
        {
            "metric": {"type": "string"},
            "driver": {"type": "string", "description": "Numeric column to band."},
            "bins": {
                "type": "integer",
                "description": "Number of quantile bands, 2 to 10 (usually 4).",
            },
            "where": _WHERE,
        },
    ),
    _tool(
        "trend",
        "A metric over time using the dataset's date column: change, slope significance and "
        'monthly seasonality. Use metric "rows" for record volume.',
        {
            "metric": {"type": "string"},
            "freq": {"type": "string", "enum": ["auto", "week", "month", "quarter"]},
            "where": _WHERE,
        },
    ),
    _tool(
        "crosstab",
        "Test whether two categorical columns are associated (Cramér's V) and show the most "
        "over-represented combination.",
        {
            "dimension_a": {"type": "string"},
            "dimension_b": {"type": "string"},
            "where": _WHERE,
        },
    ),
    _tool(
        "driver_ranking",
        "Rank every column by its association with an outcome column.",
        {"target": {"type": "string"}},
    ),
]


class ToolRunner:
    def __init__(self, frame: Frame, roles: ColumnRoles, first_id: int) -> None:
        self._frame = frame
        self._roles = roles
        self._next = first_id
        self.findings: list[Finding] = []

    def run(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Returns (content for the tool_result, is_error)."""
        try:
            finding = self._dispatch(name, args)
        except AnalysisError as e:
            return str(e), True
        except (KeyError, TypeError, ValueError) as e:
            return f"Invalid arguments for {name}: {e}", True
        finding.id = f"F{self._next}"
        finding.source = "follow_up"
        self._next += 1
        self.findings.append(finding)
        return finding_json(finding), False

    def _dispatch(self, name: str, args: dict[str, Any]) -> Finding:
        where_arg = args.get("where")
        where = Where(where_arg["column"], where_arg["value"]) if where_arg else None
        f = self._frame
        if name == "compare_segments":
            return compare_segments(f, args["metric"], args["dimension"], where=where)
        if name == "metric_by_bins":
            return metric_by_bins(
                f, args["metric"], args["driver"], int(args.get("bins") or 4), where
            )
        if name == "trend":
            metric = (
                ROWS if str(args["metric"]).lower() in ("rows", "records", ROWS) else args["metric"]
            )
            return trend(f, metric, args.get("freq") or "auto", where)
        if name == "crosstab":
            return crosstab(f, args["dimension_a"], args["dimension_b"], where)
        if name == "driver_ranking":
            target = args["target"]
            return driver_ranking(
                f,
                target,
                [d for d in self._roles.dimensions if d != target],
                [m for m in self._roles.measures if m != target],
            )
        raise AnalysisError(f"Unknown tool {name!r}.")


def finding_json(finding: Finding) -> str:
    """Compact JSON of a finding for the model (no internal ranking fields)."""
    data = finding.model_dump(exclude={"score", "source"}, exclude_none=True)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
