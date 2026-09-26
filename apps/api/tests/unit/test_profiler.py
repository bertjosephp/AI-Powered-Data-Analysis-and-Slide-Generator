import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _col(profile, name):  # type: ignore[no-untyped-def]
    return next(c for c in profile.columns if c.name == name)


@pytest.fixture
def sample_profile():  # type: ignore[no-untyped-def]
    df = load_dataset((FIXTURES / "sample.csv").read_bytes(), "sample.csv", 10**8)
    return build_profile(df, sample_rows=200_000)


def test_dataset_level_counts(sample_profile) -> None:  # type: ignore[no-untyped-def]
    p = sample_profile
    assert (p.n_rows, p.n_cols) == (40, 9)
    assert p.missing_cells_total == 5  # 3 discount + 2 region
    assert p.missing_pct_total == round(100 * 5 / 360, 2)
    assert p.duplicate_rows == 0
    assert p.sampled is False and p.sample_rows is None


def test_type_inference_on_sample(sample_profile) -> None:  # type: ignore[no-untyped-def]
    types = {c.name: c.inferred_type for c in sample_profile.columns}
    assert types == {
        "order_id": "id",
        "order_date": "datetime",
        "region": "categorical",
        "product": "categorical",
        "units": "numeric",
        "unit_price": "numeric",
        "discount": "numeric",
        "revenue": "numeric",
        "returned": "boolean",
    }
    date = _col(sample_profile, "order_date")
    assert (date.min_date, date.max_date) == ("2025-01-01T00:00:00", "2025-10-01T00:00:00")


def test_numeric_stats_are_exact() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 100.0, None]})
    x = _col(build_profile(df, 1000), "x")
    assert x.mean == 22.0
    assert x.median == 3.0
    assert (x.min, x.p25, x.p75, x.max) == (1.0, 2.0, 4.0, 100.0)
    assert x.std == round(float(pd.Series([1, 2, 3, 4, 100]).std()), 6)
    assert x.outlier_count == 1  # 100 is beyond Q3 + 1.5*IQR
    assert x.missing_count == 1 and x.missing_pct == round(100 / 6, 2)


def test_categorical_top_values_are_sorted_and_capped() -> None:
    df = pd.DataFrame({"c": ["a"] * 5 + ["b"] * 3 + [f"v{i}" for i in range(12)]})
    c = _col(build_profile(df, 1000), "c")
    assert c.inferred_type == "categorical"
    assert c.top_values is not None and len(c.top_values) == 10
    assert (c.top_values[0].value, c.top_values[0].count) == ("a", 5)
    assert (c.top_values[1].value, c.top_values[1].count) == ("b", 3)


def test_correlations_and_top_pairs() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=200)
    df = pd.DataFrame({"a": a, "b": 2 * a + 1, "neg": -a, "noise": rng.normal(size=200)})
    p = build_profile(df, 1000)
    assert p.correlation is not None
    assert p.correlation.columns == ["a", "b", "neg", "noise"]
    assert p.correlation.matrix[0][1] == 1.0
    pairs = {(x.a, x.b): x.r for x in p.top_correlations}
    assert pairs[("a", "b")] == 1.0 and pairs[("a", "neg")] == -1.0
    assert not any("noise" in key for key in pairs)


def test_output_is_json_safe_with_infinite_values() -> None:
    df = pd.DataFrame({"inf": [1.0, math.inf, -math.inf, 2.0], "k": [1, 1, 1, 1]})
    p = build_profile(df, 1000)
    json.loads(p.model_dump_json())  # strict JSON: would fail on NaN/Infinity
    dumped = p.model_dump_json()
    assert "NaN" not in dumped and "Infinity" not in dumped
    assert any("'k' is constant" in w for w in p.warnings)
    inf = _col(p, "inf")
    assert (inf.infinite_count, inf.mean, inf.max) == (2, 1.5, 2.0)
    assert any("infinite" in w for w in p.warnings)


def test_sampling_is_deterministic_and_reported() -> None:
    df = pd.DataFrame({"x": range(1000), "y": [i % 7 for i in range(1000)]})
    p1, p2 = build_profile(df, sample_rows=100), build_profile(df, sample_rows=100)
    assert p1 == p2
    assert p1.sampled and p1.sample_rows == 100 and p1.n_rows == 1000
    assert any("sample" in w for w in p1.warnings)


def test_warnings_for_missing_and_duplicates() -> None:
    df = pd.DataFrame({"a": [1, 1, None, None, None], "b": ["x", "x", "y", None, None]})
    p = build_profile(df, 1000)
    assert p.duplicate_rows == 2
    assert any("'a' is 60.0% missing" in w for w in p.warnings)
    assert any("duplicated" in w for w in p.warnings)


def test_numeric_id_only_when_named_like_id() -> None:
    df = pd.DataFrame({"customer_id": range(30), "amount": range(30)})
    types = {c.name: c.inferred_type for c in build_profile(df, 1000).columns}
    assert types == {"customer_id": "id", "amount": "numeric"}


def test_long_strings_are_text() -> None:
    df = pd.DataFrame(
        {"review": ["a fairly long free-text review " * 3 + str(i % 3) for i in range(10)]}
    )
    assert _col(build_profile(df, 1000), "review").inferred_type == "text"
