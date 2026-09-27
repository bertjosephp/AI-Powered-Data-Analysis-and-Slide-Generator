import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from app.services.analysis import stats


def test_numeric_by_groups_matches_scipy_kruskal() -> None:
    rng = np.random.default_rng(0)
    values = pd.Series(np.concatenate([rng.normal(0, 1, 50), rng.normal(1, 1, 50)]))
    groups = pd.Series(["a"] * 50 + ["b"] * 50)
    result = stats.numeric_by_groups(values, groups)
    h, p = sps.kruskal(values[:50], values[50:])
    assert result.p_value == pytest.approx(p)
    assert result.effect == pytest.approx(h / 99)
    assert result.effect_name == "epsilon squared"


def test_binary_by_groups_rate_ratio() -> None:
    outcome = pd.Series([1.0] * 30 + [0.0] * 70 + [1.0] * 10 + [0.0] * 90)
    groups = pd.Series(["hi"] * 100 + ["lo"] * 100)
    result = stats.binary_by_groups(outcome, groups)
    assert result.effect == pytest.approx(3.0)  # 30% vs 10%
    assert result.p_value is not None and result.p_value < 0.001
    assert result.strength == "strong"


def test_numeric_vs_numeric_is_spearman() -> None:
    x = pd.Series(range(100), dtype=float)
    y = x**3  # monotonic, not linear
    result = stats.numeric_vs_numeric(x, y)
    assert result.effect == pytest.approx(1.0)
    assert result.strength == "strong"


def test_binary_vs_numeric_rank_biserial_sign() -> None:
    x = pd.Series(np.arange(200, dtype=float))
    outcome = pd.Series(x > 150)  # higher x -> outcome
    result = stats.binary_vs_numeric(outcome, x)
    assert result.effect == pytest.approx(1.0)
    assert stats.binary_vs_numeric(~outcome, x).effect == pytest.approx(-1.0)


def test_cramers_v_perfect_association() -> None:
    a = pd.Series(["x", "y"] * 50)
    result = stats.categorical_vs_categorical(a, a.map({"x": "p", "y": "q"}))
    assert result.effect == pytest.approx(1.0, abs=0.02)


def test_degenerate_inputs_return_no_p_value() -> None:
    assert (
        stats.numeric_by_groups(pd.Series([1.0, 1.0, 1.0]), pd.Series(["a", "b", "a"])).p_value
        is None
    )
    assert stats.binary_vs_numeric(pd.Series([True, False]), pd.Series([1.0, 2.0])).p_value is None


def test_benjamini_hochberg_matches_reference() -> None:
    p = [0.01, 0.04, 0.03, None, 0.20]
    q = stats.benjamini_hochberg(p)
    # Reference: statsmodels multipletests(method="fdr_bh") on [0.01, 0.04, 0.03, 0.20]
    assert q[0] == pytest.approx(0.04)
    assert q[1] == pytest.approx(0.0533333, rel=1e-4)
    assert q[2] == pytest.approx(0.0533333, rel=1e-4)
    assert q[3] is None
    assert q[4] == pytest.approx(0.20)


@pytest.mark.parametrize(
    ("name", "value", "strength"),
    [
        ("Spearman rho", 0.05, "negligible"),
        ("Spearman rho", -0.2, "weak"),
        ("Spearman rho", 0.35, "moderate"),
        ("Spearman rho", -0.6, "strong"),
        ("rate ratio", 1.6, "moderate"),
        ("epsilon squared", 0.2, "strong"),
    ],
)
def test_strength_thresholds(name: str, value: float, strength: str) -> None:
    assert stats.strength_of(name, value) == strength


def test_association_scale() -> None:
    assert stats.TestResult("epsilon squared", 0.25, 0.01).association == pytest.approx(0.5)
    assert stats.TestResult("rank-biserial r", -0.4, 0.01).association == pytest.approx(0.4)
    assert math.isclose(stats.normalized("rate ratio", 2.0), 1.0)
