from app.schemas.deck import (
    ChartInsightSlide,
    ChartRef,
    ExecutiveSummarySlide,
    Kpi,
    KpiSlide,
    MetricRef,
    Takeaway,
    TitleSlide,
)
from app.schemas.insights import DeckPlan
from app.services.deck import fit
from app.services.llm.shorten import Rewrite, Rewrites, apply_rewrites, find_overlong


def _deck() -> DeckPlan:
    return DeckPlan(
        slides=[
            TitleSlide(layout="title", title="T" * (fit.TITLE + 5), subtitle="Fine"),
            ExecutiveSummarySlide(
                layout="executive_summary",
                headline="Fine",
                takeaways=[
                    Takeaway(title="Short", text="Fine"),
                    Takeaway(title="W" * (fit.CARD_TITLE + 1), text="Fine"),
                ],
            ),
            KpiSlide(
                layout="kpi_cards",
                title="Fine",
                kpis=[
                    Kpi(
                        label="L" * (fit.KPI_LABEL + 1),
                        metric=MetricRef(metric="rows", column=None, finding_id=None),
                    )
                ],
            ),
            ChartInsightSlide(
                layout="chart_insight",
                title="Fine",
                bullets=["ok", "B" * (fit.BULLET + 1)],
                chart=ChartRef(chart="finding", column=None, finding_id="F1"),
            ),
        ]
    )


def test_finds_every_overlong_field_by_path() -> None:
    found = {o.id: o.limit for o in find_overlong(_deck())}
    assert found == {
        "slides[0].title": fit.TITLE,
        "slides[1].takeaways[1].title": fit.CARD_TITLE,
        "slides[2].kpis[0].label": fit.KPI_LABEL,
        "slides[3].bullets[1]": fit.BULLET,
    }


def test_applies_only_shorter_rewrites_at_requested_ids() -> None:
    deck = _deck()
    overlong = find_overlong(deck)
    rewrites = Rewrites(
        items=[
            Rewrite(id="slides[0].title", text="A short title"),
            Rewrite(id="slides[3].bullets[1]", text="  A shorter   bullet "),
            Rewrite(id="slides[2].kpis[0].label", text="L" * 80),  # not shorter: ignored
            Rewrite(id="slides[1].headline", text="Not asked for"),  # ignored
        ]
    )
    out = apply_rewrites(deck, overlong, rewrites)
    assert out.slides[0].title == "A short title"  # type: ignore[union-attr]
    assert out.slides[3].bullets == ["ok", "A shorter bullet"]  # type: ignore[union-attr]
    assert out.slides[2].kpis[0].label == "L" * (fit.KPI_LABEL + 1)  # type: ignore[union-attr]
    assert out.slides[1].headline == "Fine"  # type: ignore[union-attr]
