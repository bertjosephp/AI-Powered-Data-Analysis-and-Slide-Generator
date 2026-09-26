from typing import Literal

from pydantic import BaseModel

InferredType = Literal["numeric", "categorical", "datetime", "boolean", "text", "id"]


class TopValue(BaseModel):
    value: str
    count: int


class ColumnProfile(BaseModel):
    name: str
    inferred_type: InferredType
    dtype: str
    missing_count: int
    missing_pct: float
    unique_count: int

    # numeric
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    max: float | None = None
    skew: float | None = None
    outlier_count: int | None = None
    infinite_count: int | None = None

    # categorical / boolean
    top_values: list[TopValue] | None = None

    # datetime
    min_date: str | None = None
    max_date: str | None = None


class CorrelationMatrix(BaseModel):
    method: Literal["pearson"] = "pearson"
    columns: list[str]
    matrix: list[list[float | None]]


class CorrelationPair(BaseModel):
    a: str
    b: str
    r: float


class DatasetProfile(BaseModel):
    n_rows: int
    n_cols: int
    memory_bytes: int
    duplicate_rows: int
    missing_cells_total: int
    missing_pct_total: float
    sampled: bool
    sample_rows: int | None = None
    columns: list[ColumnProfile]
    correlation: CorrelationMatrix | None = None
    top_correlations: list[CorrelationPair]
    warnings: list[str]
