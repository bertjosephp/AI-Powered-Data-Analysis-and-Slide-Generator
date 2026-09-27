from functools import cache
from pathlib import Path

from app.schemas.deck import ChartInsightSlide, ChartRef
from app.schemas.findings import Finding
from app.schemas.insights import Insights, KeyFinding
from app.schemas.profile import DatasetProfile
from app.services.analysis.analyses import compare_segments
from app.services.analysis.battery import run_battery
from app.services.eda.profiler import build_profile
from app.services.ingestion.loader import load_dataset
from app.services.llm.grounding import _NUMBER, check_grounding

FIXTURES = Path(__file__).parent.parent / "fixtures"
DATA = Path(__file__).parents[2] / "app" / "sample_data"


@cache
def _evidence() -> tuple[DatasetProfile, tuple[Finding, ...], Finding]:
    df = load_dataset((DATA / "ecommerce_orders.csv").read_bytes(), "e.csv", 10**8)
    profile = build_profile(df, 200_000)
    battery = run_battery(df, profile)
    social = compare_segments(battery.frame, "returned", "channel")
    social.id = "F99"
    return profile, (*battery.findings, social), social


def _insights(detail: str) -> Insights:
    base = Insights.model_validate_json((FIXTURES / "llm_response.json").read_text())
    return base.model_copy(
        update={
            "executive_summary": "Summary.",
            "key_findings": [KeyFinding(title="t", detail=detail, finding_ids=["F99"])],
            "questions_answered": [],
            "open_questions": [],
            "hypotheses": [],
            "recommended_actions": [],
            "data_quality_notes": [],
            "slides": [],
        }
    )


def _check(detail: str):  # type: ignore[no-untyped-def]
    profile, findings, _ = _evidence()
    return check_grounding(_insights(detail), profile, list(findings))


def test_numbers_from_findings_are_verified_at_printed_precision() -> None:
    _, _, social = _evidence()
    top, bottom = social.facts["top_value"], social.facts["bottom_value"]
    report = _check(
        f"Social orders are returned {top:.1f}% of the time vs {bottom:.0f}% for Paid Search, "
        f"about {top / bottom:.1f}× as often."
    )
    assert report.checked == 3 and report.unverified == []


def test_invented_numbers_are_flagged_with_context() -> None:
    report = _check("Returns cost the company 4,321,987 dollars and rose 73.4% last year.")
    values = [u.value for u in report.unverified]
    assert "4,321,987" in values and "73.4%" in values
    assert all(u.location == "key_findings[0].detail" for u in report.unverified)
    assert "73.4%" in report.unverified[-1].context


def test_small_counts_years_ids_and_column_names_are_ignored() -> None:
    report = _check("In 2025 the top 3 channels (see F12) drove readmitted_30d and Q4 volume.")
    assert report.checked == 0


def test_slide_text_is_checked_too() -> None:
    profile, findings, social = _evidence()
    base = _insights("Nothing numeric here.")
    slide = ChartInsightSlide(
        layout="chart_insight",
        title="Social returns stand out",
        bullets=[
            f"Social: {social.facts['top_value']:.1f}% returned.",
            "An invented 987.65 figure.",
        ],
        chart=ChartRef(chart="finding", column=None, finding_id=social.id),
    )
    report = check_grounding(base.model_copy(update={"slides": [slide]}), profile, list(findings))
    assert report.checked == 2
    assert [(u.location, u.value) for u in report.unverified] == [
        ("slides[0].bullets[1]", "987.65")
    ]


def test_p_values_are_verified_and_thresholds_ignored() -> None:
    _, findings, _ = _evidence()
    p = next(f.p_value for f in findings if f.p_value is not None and 0.001 < f.p_value < 1)
    report = _check(
        f"This one is weaker (p={p:.2f}); the effect is strong (p < 0.001, "
        "and a second test gave p≈2e-232)."
    )
    assert report.unverified == [] and report.checked == 1


def test_category_labels_and_complements_count_as_evidence() -> None:
    profile, findings, social = _evidence()
    label = next(c for f in findings for c in f.chart.categories if "%" in c or "-" in c)
    number = next(m.group(1) for m in _NUMBER.finditer(label))
    missing = next(c for c in profile.columns if 0 < c.missing_pct < 100)
    top = social.facts["top_value"]
    report = _check(
        f"The {number} band matters. {100 - missing.missing_pct:.1f}% of rows have "
        f"{missing.name}, and {100 - top:.1f}% of Social orders are kept."
    )
    assert report.unverified == [], report.unverified


def test_values_of_percent_named_columns_may_be_written_with_a_percent_sign() -> None:
    profile, findings, _ = _evidence()
    col = next(c for c in profile.columns if c.name == "discount_pct")
    assert col.max is not None
    report = _check(f"Margin collapses at a {col.max:.0f}% discount.")
    assert report.checked == 1 and report.unverified == []
