"""Effect sizes and significance tests, each returning (effect, p-value).

Rank-based tests are used throughout: business data is skewed and full of
outliers, and these make no normality assumption.
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from app.schemas.findings import Strength

# (weak, moderate, strong) thresholds per effect measure, from common conventions
# (Cohen; Tomczak & Tomczak 2014 for epsilon squared).
THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "epsilon squared": (0.01, 0.06, 0.14),
    "Spearman rho": (0.1, 0.3, 0.5),
    "rank-biserial r": (0.1, 0.3, 0.5),
    "Cramer's V": (0.1, 0.2, 0.35),
    "rate ratio": (1.25, 1.5, 2.0),
    "top-20% share": (0.35, 0.5, 0.65),
    "seasonal ratio": (1.2, 1.4, 1.7),
}


@dataclass(frozen=True)
class TestResult:
    effect_name: str
    effect: float
    p_value: float | None

    @property
    def strength(self) -> Strength:
        return strength_of(self.effect_name, self.effect)

    @property
    def association(self) -> float:
        """Effect on a common 0..1 association scale, for ranking drivers."""
        if self.effect_name == "epsilon squared":
            return math.sqrt(max(self.effect, 0.0))
        return min(abs(self.effect), 1.0)


def strength_of(effect_name: str, value: float) -> Strength:
    weak, moderate, strong = THRESHOLDS[effect_name]
    v = abs(value)
    if v >= strong:
        return "strong"
    if v >= moderate:
        return "moderate"
    if v >= weak:
        return "weak"
    return "negligible"


def normalized(effect_name: str, value: float) -> float:
    """0 at the 'weak' threshold's baseline, 1 at 'strong'; capped at 1.5."""
    weak, _, strong = THRESHOLDS[effect_name]
    base = 1.0 if effect_name in ("rate ratio", "seasonal ratio") else 0.0
    return float(min(max((abs(value) - base) / (strong - base), 0.0), 1.5))


def numeric_by_groups(values: pd.Series, groups: pd.Series) -> TestResult:
    """Kruskal-Wallis H with epsilon-squared effect size."""
    samples = [values[groups == g].to_numpy() for g in groups.unique()]
    samples = [s for s in samples if len(s) > 0]
    n = sum(len(s) for s in samples)
    if len(samples) < 2 or n < 3 or np.ptp(np.concatenate(samples)) == 0:
        return TestResult("epsilon squared", 0.0, None)
    h, p = stats.kruskal(*samples)
    return TestResult("epsilon squared", float(h) / (n - 1), float(p))


def binary_by_groups(outcome: pd.Series, groups: pd.Series) -> TestResult:
    """Chi-square test of independence; effect is the highest/lowest group rate ratio."""
    table = pd.crosstab(groups, outcome)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return TestResult("rate ratio", 1.0, None)
    _, p, _, _ = stats.chi2_contingency(table.to_numpy())
    rates = outcome.groupby(groups).mean()
    low = rates.min()
    ratio = (
        float(rates.max() / low) if low > 0 else float(rates.max() / max(1 / len(outcome), 1e-9))
    )
    return TestResult("rate ratio", ratio, float(p))


def numeric_vs_numeric(x: pd.Series, y: pd.Series) -> TestResult:
    frame = pd.concat([x, y], axis=1).dropna()
    if len(frame) < 5 or frame.iloc[:, 0].nunique() < 2 or frame.iloc[:, 1].nunique() < 2:
        return TestResult("Spearman rho", 0.0, None)
    rho, p = stats.spearmanr(frame.iloc[:, 0], frame.iloc[:, 1])
    return TestResult("Spearman rho", float(rho), float(p))


def binary_vs_numeric(outcome: pd.Series, x: pd.Series) -> TestResult:
    """Mann-Whitney U; rank-biserial r > 0 means higher x goes with the outcome."""
    frame = pd.concat([outcome.astype(bool), x], axis=1).dropna()
    pos = frame[frame.iloc[:, 0]].iloc[:, 1].to_numpy()
    neg = frame[~frame.iloc[:, 0]].iloc[:, 1].to_numpy()
    if len(pos) < 3 or len(neg) < 3:
        return TestResult("rank-biserial r", 0.0, None)
    u, p = stats.mannwhitneyu(pos, neg, alternative="two-sided")
    r = 2 * float(u) / (len(pos) * len(neg)) - 1
    return TestResult("rank-biserial r", r, float(p))


def categorical_vs_categorical(a: pd.Series, b: pd.Series) -> TestResult:
    table = pd.crosstab(a, b)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return TestResult("Cramer's V", 0.0, None)
    _, p, _, _ = stats.chi2_contingency(table.to_numpy())
    # Effect size from the uncorrected statistic (Yates' correction would shrink V).
    chi2, _, _, _ = stats.chi2_contingency(table.to_numpy(), correction=False)
    n = table.to_numpy().sum()
    v = math.sqrt(float(chi2) / (n * (min(table.shape) - 1)))
    return TestResult("Cramer's V", v, float(p))


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """FDR-adjusted q-values; None entries (untested) stay None."""
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None]
    if not indexed:
        return list(p_values)
    m = len(indexed)
    order = sorted(indexed, key=lambda t: t[1])
    q: list[float | None] = [None] * len(p_values)
    running = 1.0
    for rank in range(m, 0, -1):
        i, p = order[rank - 1]
        running = min(running, p * m / rank)
        q[i] = min(running, 1.0)
    return q
