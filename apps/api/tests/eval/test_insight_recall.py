"""Insight-recall eval: does the battery find what was planted in the sample datasets?

Each dataset's manifest (app/sample_data/*.expected.json) lists planted
relationships. Primary ones must appear among the battery's ranked findings;
secondary ones (a step removed from the outcome) must be confirmed by a direct
analysis. Noise columns must never be reported as significant.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from app.schemas.findings import Finding
from app.services.analysis.analyses import compare_segments, metric_by_bins
from app.services.analysis.battery import BatteryResult, run_battery
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset

DATA = Path(__file__).parents[2] / "app" / "sample_data"
MANIFESTS = {
    p.name.removesuffix(".expected.json"): json.loads(p.read_text())
    for p in sorted(DATA.glob("*.expected.json"))
}


@cache
def _battery(name: str) -> BatteryResult:
    df = load_dataset((DATA / f"{name}.csv").read_bytes(), f"{name}.csv", 10**8)
    return run_battery(df, build_profile(df, 200_000))


def _matches(finding: Finding, planted: dict[str, Any]) -> bool:
    kind = planted["kind"]
    if kind == "segment":
        if (finding.kind, finding.target, finding.dimension) != (
            "segment",
            planted["target"],
            planted["dimension"],
        ):
            return False
        if "top" in planted:
            return finding.facts.get("top") == planted["top"]
        return finding.facts.get("bottom") == planted["bottom"]
    if kind == "bins":
        if (finding.kind, finding.target, finding.dimension) != (
            "bins",
            planted["target"],
            planted["driver"],
        ):
            return False
        first, last = float(finding.facts["first_value"]), float(finding.facts["last_value"])
        return last > first if planted["direction"] == "increasing" else last < first
    if kind == "seasonality":
        expected = {
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][
                m - 1
            ]
            for m in planted["peak_months"]
        }
        return finding.kind == "trend" and set(finding.facts.get("peak_months", [])) == expected
    if kind == "concentration":
        return (
            finding.kind == "concentration"
            and finding.target == planted["target"]
            and float(finding.facts["top10_share"]) >= planted["top10_share_min"]
        )
    raise AssertionError(f"unknown planted kind {kind}")


PRIMARY = [
    (name, p)
    for name, manifest in MANIFESTS.items()
    for p in manifest["planted"]
    if p["kind"] != "null" and p.get("tier", "primary") == "primary"
]


def test_manifests_exist_for_every_dataset() -> None:
    assert set(MANIFESTS) == {
        "ecommerce_orders",
        "saas_churn",
        "hr_attrition",
        "hospital_readmissions",
    }


@pytest.mark.parametrize(
    ("dataset", "planted"), PRIMARY, ids=[f"{d}:{p['id']}" for d, p in PRIMARY]
)
def test_battery_recovers_planted_insight(dataset: str, planted: dict[str, Any]) -> None:
    findings = _battery(dataset).findings
    assert any(_matches(f, planted) for f in findings), (
        f"{planted['id']} not found. Findings: " + "; ".join(f"{f.id} {f.title}" for f in findings)
    )


@pytest.mark.parametrize("dataset", sorted(MANIFESTS))
def test_noise_columns_are_never_significant_findings(dataset: str) -> None:
    noise = set(MANIFESTS[dataset]["noise_columns"])
    flagged = [f for f in _battery(dataset).findings if {f.target, f.dimension} & noise]
    assert not flagged, [f.title for f in flagged]


@pytest.mark.parametrize("dataset", sorted(MANIFESTS))
def test_findings_are_significant_ranked_and_labelled(dataset: str) -> None:
    findings = _battery(dataset).findings
    assert 6 <= len(findings) <= 15
    assert [f.id for f in findings] == [f"F{i}" for i in range(1, len(findings) + 1)]
    assert [f.score for f in findings] == sorted((f.score for f in findings), reverse=True)
    for f in findings:
        assert f.significant
        assert f.q_value is None or f.q_value < 0.05
        assert f.summary and f.headline and f.chart.categories


def test_secondary_and_null_patterns_via_direct_analysis() -> None:
    for name, manifest in MANIFESTS.items():
        frame = _battery(name).frame
        for planted in manifest["planted"]:
            if planted["kind"] == "null":
                assert not metric_by_bins(frame, planted["target"], planted["driver"]).significant
            elif planted.get("tier") == "secondary":
                f = compare_segments(frame, planted["target"], planted["dimension"])
                assert f.significant and f.facts["top"] == planted["top"]


def test_battery_is_deterministic() -> None:
    df = load_dataset((DATA / "saas_churn.csv").read_bytes(), "saas_churn.csv", 10**8)
    a = run_battery(df, build_profile(df, 200_000)).findings
    b = run_battery(df, build_profile(df, 200_000)).findings
    assert [f.model_dump() for f in a] == [f.model_dump() for f in b]
