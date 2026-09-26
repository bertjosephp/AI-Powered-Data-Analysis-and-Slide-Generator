"""ResolvedSlide list -> .pptx bytes, drawn from scratch with python-pptx.

No template file: every layout is placed on a 16:9 grid from the Theme tokens,
so the design is versioned and testable. Charts are native PowerPoint charts
(editable, with their data embedded) and every figure on a slide comes from the
resolver, never from the model.
"""

import io
from collections.abc import Callable
from typing import Protocol

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.slide import Slide
from pptx.util import Emu, Inches, Pt

from app.schemas.deck import (
    ExecutiveSummarySlide,
    HypothesesSlide,
    NextStepsSlide,
    ResolvedChart,
    ResolvedChartInsightSlide,
    ResolvedKpiSlide,
    ResolvedSlide,
    ResolvedTitleSlide,
)
from app.services.deck.resolve import format_number, format_percent
from app.services.deck.theme import DEFAULT_THEME, Theme, rgb

BLANK_LAYOUT = 6


class DeckRenderer(Protocol):
    def render(self, slides: list[ResolvedSlide], dataset_name: str) -> bytes: ...


class PptxRenderer:
    def __init__(self, theme: Theme = DEFAULT_THEME) -> None:
        self.t = theme

    def render(self, slides: list[ResolvedSlide], dataset_name: str) -> bytes:
        prs = Presentation()
        prs.slide_width, prs.slide_height = self.t.width, self.t.height
        total = len(slides)
        for index, spec in enumerate(slides, start=1):
            slide = prs.slides.add_slide(prs.slide_layouts[BLANK_LAYOUT])
            draw = self._drawer(spec)
            draw(slide, spec)
            if not isinstance(spec, ResolvedTitleSlide | NextStepsSlide):
                self._footer(slide, dataset_name, index, total)
        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()

    def _drawer(self, spec: ResolvedSlide) -> Callable[[Slide, ResolvedSlide], None]:
        drawers: dict[type, Callable[[Slide, ResolvedSlide], None]] = {
            ResolvedTitleSlide: self._title,  # type: ignore[dict-item]
            ExecutiveSummarySlide: self._executive_summary,  # type: ignore[dict-item]
            ResolvedKpiSlide: self._kpis,  # type: ignore[dict-item]
            ResolvedChartInsightSlide: self._chart_insight,  # type: ignore[dict-item]
            HypothesesSlide: self._hypotheses,  # type: ignore[dict-item]
            NextStepsSlide: self._next_steps,  # type: ignore[dict-item]
        }
        return drawers[type(spec)]

    # ---------- layouts ----------

    def _title(self, slide: Slide, s: ResolvedTitleSlide) -> None:
        t = self.t
        self._background(slide, t.dark_bg)
        self._rect(slide, 0, 0, Inches(0.22), t.height, t.accent)
        left, width = Inches(1.1), Inches(10.6)
        self._rect(slide, left, Inches(2.05), Inches(1.1), Inches(0.07), t.accent_on_dark)
        self._text(
            slide,
            left,
            Inches(2.35),
            width,
            Inches(1.9),
            s.title,
            46,
            t.on_dark,
            bold=True,
            anchor=MSO_ANCHOR.BOTTOM,
            line_spacing=1.0,
        )
        self._text(slide, left, Inches(4.4), width, Inches(1.1), s.subtitle, 20, t.on_dark_muted)
        self._text(slide, left, Inches(6.45), width, Inches(0.4), s.meta, 12, t.on_dark_muted)
        self._notes(slide, f"{s.title}\n{s.subtitle}\n{s.meta}")

    def _executive_summary(self, slide: Slide, s: ExecutiveSummarySlide) -> None:
        t = self.t
        self._background(slide, t.canvas)
        self._eyebrow(slide, "Executive summary")
        self._text(
            slide,
            t.margin,
            Inches(0.85),
            t.content_width,
            Inches(1.45),
            s.headline,
            26,
            t.ink,
            bold=True,
            line_spacing=1.05,
        )
        cols = self._columns(len(s.takeaways) or 1)
        top, height = Inches(2.6), Inches(3.75)
        for i, (x, w) in enumerate(cols[: len(s.takeaways)]):
            item = s.takeaways[i]
            self._card(slide, x, top, w, height)
            pad = Inches(0.3)
            self._text(
                slide,
                x + pad,
                top + pad,
                w - 2 * pad,
                Inches(0.4),
                f"{i + 1:02d}",
                14,
                t.accent,
                bold=True,
            )
            self._text(
                slide,
                x + pad,
                top + Inches(0.8),
                w - 2 * pad,
                Inches(0.9),
                item.title,
                19,
                t.ink,
                bold=True,
                line_spacing=1.05,
            )
            self._text(
                slide,
                x + pad,
                top + Inches(1.75),
                w - 2 * pad,
                Inches(1.8),
                item.text,
                14,
                t.muted,
                line_spacing=1.15,
            )
        self._notes(
            slide, "\n".join([s.headline, *(f"- {k.title}: {k.text}" for k in s.takeaways)])
        )

    def _kpis(self, slide: Slide, s: ResolvedKpiSlide) -> None:
        t = self.t
        self._content_header(slide, s.title, "Key metrics")
        if not s.kpis:
            self._text(
                slide,
                t.margin,
                Inches(2.4),
                t.content_width,
                Inches(1),
                "No metrics available.",
                18,
                t.muted,
            )
            return
        top, height = Inches(2.35), Inches(2.9)
        for (x, w), kpi in zip(self._columns(len(s.kpis)), s.kpis, strict=False):
            self._card(slide, x, top, w, height)
            self._rect(slide, x, top, w, Inches(0.08), t.accent)
            pad = Inches(0.32)
            self._text(
                slide,
                x + pad,
                top + Inches(0.35),
                w - 2 * pad,
                Inches(0.62),
                kpi.label,
                14,
                t.muted,
                bold=True,
                line_spacing=1.0,
            )
            self._text(
                slide,
                x + pad,
                top + Inches(1.0),
                w - 2 * pad,
                Inches(1.05),
                kpi.value,
                self._kpi_size(kpi.value, len(s.kpis)),
                t.ink,
                bold=True,
                anchor=MSO_ANCHOR.MIDDLE,
            )
            self._text(
                slide,
                x + pad,
                top + Inches(2.1),
                w - 2 * pad,
                Inches(0.6),
                kpi.caption,
                12,
                t.muted,
            )
        self._notes(slide, "\n".join(f"{k.label}: {k.value} ({k.caption})" for k in s.kpis))

    def _chart_insight(self, slide: Slide, s: ResolvedChartInsightSlide) -> None:
        t = self.t
        self._content_header(slide, s.title, "Insight")
        top, height = Inches(1.95), Inches(4.65)
        if s.chart is None:
            self._bullet_cards(
                slide, s.bullets, t.margin, top, t.content_width, height, horizontal=True
            )
            return
        chart_w = Inches(7.55)
        self._card(slide, t.margin, top, chart_w, height)
        pad = Inches(0.3)
        self._text(
            slide,
            t.margin + pad,
            top + Inches(0.22),
            chart_w - 2 * pad,
            Inches(0.4),
            s.chart.caption,
            13,
            t.muted,
            bold=True,
        )
        self._chart(
            slide,
            s.chart,
            t.margin + Inches(0.15),
            top + Inches(0.7),
            chart_w - Inches(0.3),
            height - Inches(0.85),
        )
        side_x = t.margin + chart_w + t.gutter
        self._bullet_cards(
            slide, s.bullets, side_x, top, t.width - t.margin - side_x, height, horizontal=False
        )
        data = ", ".join(
            f"{c}: {self._format(v, s.chart.value_format)}"
            for c, v in zip(s.chart.categories, s.chart.values, strict=True)
        )
        self._notes(slide, "\n".join([*s.bullets, f"{s.chart.caption}. {data}"]))

    def _hypotheses(self, slide: Slide, s: HypothesesSlide) -> None:
        t = self.t
        self._content_header(slide, s.title, "Hypotheses to test")
        top, height = Inches(1.95), Inches(4.65)
        for (x, w), h in zip(self._columns(len(s.items) or 1), s.items, strict=False):
            self._card(slide, x, top, w, height)
            pad = Inches(0.3)
            self._pill(
                slide, x + pad, top + pad, f"{h.confidence.capitalize()} confidence", h.confidence
            )
            self._text(
                slide,
                x + pad,
                top + Inches(0.95),
                w - 2 * pad,
                Inches(1.9),
                h.statement,
                17,
                t.ink,
                bold=True,
                line_spacing=1.08,
            )
            self._rect(slide, x + pad, top + Inches(2.95), w - 2 * pad, Emu(9525), t.card_border)
            self._text(
                slide,
                x + pad,
                top + Inches(3.1),
                w - 2 * pad,
                Inches(0.3),
                "HOW TO TEST",
                10,
                t.muted,
                bold=True,
            )
            self._text(
                slide,
                x + pad,
                top + Inches(3.4),
                w - 2 * pad,
                Inches(1.1),
                h.test,
                13,
                t.muted,
                line_spacing=1.1,
            )
        self._notes(slide, "\n".join(f"- {h.statement} (test: {h.test})" for h in s.items))

    def _next_steps(self, slide: Slide, s: NextStepsSlide) -> None:
        t = self.t
        self._background(slide, t.dark_bg)
        left = Inches(1.1)
        self._rect(slide, left, Inches(0.85), Inches(1.1), Inches(0.07), t.accent_on_dark)
        self._text(
            slide,
            left,
            Inches(1.05),
            Inches(11.2),
            Inches(1.3),
            s.title,
            32,
            t.on_dark,
            bold=True,
            line_spacing=1.0,
        )
        row_h = Inches(1.1)
        for i, step in enumerate(s.steps):
            y = Inches(2.6) + i * row_h
            circle = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, left, Emu(y), Inches(0.62), Inches(0.62)
            )
            self._fill(circle, t.accent)
            self._shape_text(circle, str(i + 1), 18, t.on_dark, bold=True)
            self._text(
                slide,
                left + Inches(0.95),
                y - Inches(0.05),
                Inches(10),
                Inches(0.75),
                step,
                20,
                t.on_dark,
                anchor=MSO_ANCHOR.MIDDLE,
            )
        self._notes(slide, "\n".join(f"{i + 1}. {step}" for i, step in enumerate(s.steps)))

    # ---------- components ----------

    def _content_header(self, slide: Slide, title: str, eyebrow: str) -> None:
        self._background(slide, self.t.canvas)
        self._eyebrow(slide, eyebrow)
        self._text(
            slide,
            self.t.margin,
            Inches(0.78),
            self.t.content_width,
            Inches(1.05),
            title,
            28,
            self.t.ink,
            bold=True,
            line_spacing=1.0,
        )

    def _eyebrow(self, slide: Slide, text: str) -> None:
        t = self.t
        self._rect(slide, t.margin, Inches(0.5), Inches(0.35), Inches(0.06), t.accent)
        self._text(
            slide,
            t.margin + Inches(0.5),
            Inches(0.36),
            Inches(6),
            Inches(0.35),
            text.upper(),
            11,
            t.accent,
            bold=True,
        )

    def _footer(self, slide: Slide, dataset_name: str, index: int, total: int) -> None:
        t = self.t
        y, h = t.height - Inches(0.55), Inches(0.3)
        self._text(
            slide,
            t.margin,
            y,
            Inches(8),
            h,
            f"{dataset_name} · figures computed from the data with pandas",
            10,
            t.muted,
        )
        self._text(
            slide,
            t.width - t.margin - Inches(2),
            y,
            Inches(2),
            h,
            f"{index} / {total}",
            10,
            t.muted,
            align=PP_ALIGN.RIGHT,
        )

    def _bullet_cards(
        self, slide: Slide, bullets: list[str], x: int, y: int, w: int, h: int, *, horizontal: bool
    ) -> None:
        t = self.t
        if not bullets:
            return
        n = len(bullets)
        gap = t.gutter
        for i, text in enumerate(bullets):
            if horizontal:
                cw = int((w - gap * (n - 1)) / n)
                cx, cy, ch = x + i * (cw + gap), y, h
            else:
                ch = int((h - gap * (n - 1)) / n)
                cx, cy, cw = x, y + i * (ch + gap), w
            self._card(slide, cx, cy, cw, ch)
            self._rect(
                slide,
                cx,
                cy + Inches(0.25),
                Inches(0.07),
                min(ch - Inches(0.5), Inches(0.9)),
                t.accent,
            )
            pad = Inches(0.3)
            self._text(
                slide,
                cx + pad,
                cy + Inches(0.2),
                cw - pad - Inches(0.25),
                ch - Inches(0.4),
                text,
                15 if horizontal else 13,
                t.ink,
                line_spacing=1.12,
            )

    def _chart(self, slide: Slide, chart: ResolvedChart, x: int, y: int, w: int, h: int) -> None:
        t = self.t
        data = CategoryChartData()  # type: ignore[no-untyped-call]
        data.categories = chart.categories
        data.add_series(chart.caption, chart.values)  # type: ignore[no-untyped-call]
        vertical = chart.kind == "numeric_summary"
        kind = XL_CHART_TYPE.COLUMN_CLUSTERED if vertical else XL_CHART_TYPE.BAR_CLUSTERED
        frame = slide.shapes.add_chart(kind, Emu(x), Emu(y), Emu(w), Emu(h), data)  # type: ignore[arg-type]
        c = frame.chart  # type: ignore[attr-defined]  # stubs say Chart; it returns a GraphicFrame
        c.has_legend = False
        c.has_title = False
        c.font.name, c.font.size, c.font.color.rgb = t.font, Pt(12), rgb(t.muted)

        plot = c.plots[0]
        plot.gap_width = 55
        value_axis, category_axis = c.value_axis, c.category_axis
        value_axis.visible = False
        value_axis.has_major_gridlines = False
        value_axis.has_minor_gridlines = False
        category_axis.has_major_gridlines = False
        category_axis.format.line.color.rgb = rgb(t.card_border)
        category_axis.tick_labels.font.size = Pt(12)
        if not vertical:
            category_axis.reverse_order = True  # largest bar on top, as in the source order
        if chart.kind == "correlations":
            # Diverging axis only when both signs are present; r keeps its 0..1 scale.
            low = -1.15 if any(v < 0 for v in chart.values) else 0
            value_axis.minimum_scale, value_axis.maximum_scale = low, 1.15
        else:
            value_axis.minimum_scale = 0
            value_axis.maximum_scale = max(chart.values) * 1.2 if chart.values else 1

        series = plot.series[0]
        series.invert_if_negative = False
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = rgb(t.accent)
        for i, value in enumerate(chart.values):
            point = series.points[i]
            if chart.kind == "correlations":
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = rgb(t.positive if value >= 0 else t.negative)
            label = point.data_label
            label.position = XL_LABEL_POSITION.OUTSIDE_END
            label.text_frame.text = self._format(value, chart.value_format)
            run = label.text_frame.paragraphs[0].runs[0]
            run.font.size, run.font.bold, run.font.color.rgb = Pt(12), True, rgb(t.ink)
            run.font.name = t.font

    def _pill(self, slide: Slide, x: int, y: int, text: str, level: str) -> None:
        t = self.t
        fill, color = {
            "high": (t.accent, "#FFFFFF"),
            "medium": (t.accent_soft, t.accent),
            "low": ("#EEEEF1", t.muted),
        }[level]
        pill = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Emu(x), Emu(y), Inches(1.75), Inches(0.36)
        )
        pill.adjustments[0] = 0.5
        self._fill(pill, fill)
        self._shape_text(pill, text, 11, color, bold=True)

    def _card(self, slide: Slide, x: int, y: int, w: int, h: int) -> None:
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
        card.adjustments[0] = self.t.corner
        self._fill(card, self.t.card, border=self.t.card_border)

    # ---------- primitives ----------

    def _columns(self, n: int) -> list[tuple[int, int]]:
        t = self.t
        w = int((t.content_width - t.gutter * (n - 1)) / n)
        return [(int(t.margin + i * (w + t.gutter)), w) for i in range(n)]

    @staticmethod
    def _kpi_size(value: str, count: int) -> int:
        size = 48 if count <= 3 else 42
        return size - 8 if len(value) > 7 else size

    def _background(self, slide: Slide, color: str) -> None:
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = rgb(color)

    def _rect(self, slide: Slide, x: int, y: int, w: int, h: int, color: str) -> None:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
        self._fill(shape, color)

    @staticmethod
    def _fill(shape, color: str, border: str | None = None) -> None:  # type: ignore[no-untyped-def]
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(color)
        if border:
            shape.line.color.rgb = rgb(border)
            shape.line.width = Pt(0.75)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False

    def _text(
        self,
        slide: Slide,
        x: int,
        y: int,
        w: int,
        h: int,
        text: str,
        size: int,
        color: str,
        *,
        bold: bool = False,
        align: PP_ALIGN = PP_ALIGN.LEFT,
        anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
        line_spacing: float = 1.1,
    ) -> None:
        box = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
        frame = box.text_frame
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.vertical_anchor = anchor
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        paragraph = frame.paragraphs[0]
        paragraph.alignment = align
        paragraph.line_spacing = line_spacing
        run = paragraph.add_run()
        run.text = text
        font = run.font
        font.name, font.size, font.bold, font.color.rgb = self.t.font, Pt(size), bold, rgb(color)

    def _shape_text(self, shape, text: str, size: int, color: str, *, bold: bool = False) -> None:  # type: ignore[no-untyped-def]
        frame = shape.text_frame
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = text
        run.font.name, run.font.size, run.font.bold = self.t.font, Pt(size), bold
        run.font.color.rgb = rgb(color)

    @staticmethod
    def _notes(slide: Slide, text: str) -> None:
        frame = slide.notes_slide.notes_text_frame
        if frame is not None:
            frame.text = text

    @staticmethod
    def _format(value: float, kind: str) -> str:
        if kind == "percent":
            return format_percent(value)
        if kind == "correlation":
            return f"{value:.2f}"
        return format_number(value)
