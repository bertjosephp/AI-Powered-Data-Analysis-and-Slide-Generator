// Browser rendering of one resolved slide. Geometry and type sizes mirror
// apps/api/app/services/deck/pptx_renderer.py (inches and points on a 13.333in
// canvas), expressed in container-query units so one component scales from a
// thumbnail to full screen. Colors are the deck theme's, not the app's, so the
// preview matches the downloaded file in light and dark mode alike.
import type { CSSProperties, ReactNode } from "react";

import type { Chart, Slide } from "@/lib/api/types";

const DECK = {
  darkBg: "#101016",
  canvas: "#F6F6F8",
  card: "#FFFFFF",
  cardBorder: "#E4E4EA",
  ink: "#16161D",
  muted: "#5F6070",
  onDark: "#F2F2F6",
  onDarkMuted: "#A3A3B5",
  accent: "#4F46E5",
  accentSoft: "#EEF0FF",
  accentOnDark: "#8B85FF",
  positive: "#2A78D6",
  negative: "#E34948",
};

const SLIDE_WIDTH_IN = 13.333;
const MARGIN = 0.6;
const GUTTER = 0.3;
const CONTENT_W = SLIDE_WIDTH_IN - 2 * MARGIN;

/** inches -> container-query width units */
const u = (inches: number) => `${(inches / SLIDE_WIDTH_IN) * 100}cqw`;
/** points -> container-query width units (72pt per inch) */
const pt = (points: number) => u(points / 72);

function box(x: number, y: number, w: number, h: number): CSSProperties {
  return { position: "absolute", left: u(x), top: u(y), width: u(w), height: u(h) };
}

function Text({
  at,
  size,
  color,
  bold,
  leading = 1.1,
  anchor = "top",
  align = "left",
  children,
}: {
  at: CSSProperties;
  size: number;
  color: string;
  bold?: boolean;
  leading?: number;
  anchor?: "top" | "middle" | "bottom";
  align?: "left" | "right" | "center";
  children: ReactNode;
}) {
  return (
    <div
      style={{
        ...at,
        display: "flex",
        flexDirection: "column",
        justifyContent: { top: "flex-start", middle: "center", bottom: "flex-end" }[anchor],
        fontSize: pt(size),
        lineHeight: leading * 1.2,
        fontWeight: bold ? 700 : 400,
        color,
        textAlign: align,
        overflow: "hidden",
      }}
    >
      <span>{children}</span>
    </div>
  );
}

function Rect({ at, color, radius = 0, border }: { at: CSSProperties; color: string; radius?: number; border?: string }) {
  return (
    <div
      aria-hidden
      style={{
        ...at,
        background: color,
        borderRadius: radius ? u(radius) : undefined,
        border: border ? `1px solid ${border}` : undefined,
      }}
    />
  );
}

function columns(n: number): Array<[number, number]> {
  const w = (CONTENT_W - GUTTER * (n - 1)) / n;
  return Array.from({ length: n }, (_, i) => [MARGIN + i * (w + GUTTER), w]);
}

type Props = { slide: Slide; index: number; total: number; datasetName: string };

export function SlideView({ slide, index, total, datasetName }: Props) {
  const dark = slide.layout === "title" || slide.layout === "next_steps";
  return (
    <div
      className="relative aspect-video w-full overflow-hidden font-sans select-none [container-type:inline-size]"
      style={{ background: dark ? DECK.darkBg : DECK.canvas }}
    >
      <Layout slide={slide} />
      {!dark && (
        <>
          <Text at={box(MARGIN, 6.95, 8, 0.3)} size={10} color={DECK.muted}>
            {datasetName} · figures computed from the data with pandas
          </Text>
          <Text at={box(SLIDE_WIDTH_IN - MARGIN - 2, 6.95, 2, 0.3)} size={10} color={DECK.muted} align="right">
            {index} / {total}
          </Text>
        </>
      )}
    </div>
  );
}

function Layout({ slide }: { slide: Slide }) {
  switch (slide.layout) {
    case "title":
      return (
        <>
          <Rect at={box(0, 0, 0.22, 7.5)} color={DECK.accent} />
          <Rect at={box(1.1, 2.05, 1.1, 0.07)} color={DECK.accentOnDark} />
          <Text at={box(1.1, 2.35, 10.6, 1.9)} size={46} color={DECK.onDark} bold leading={1} anchor="bottom">
            {slide.title}
          </Text>
          <Text at={box(1.1, 4.4, 10.6, 1.1)} size={20} color={DECK.onDarkMuted}>
            {slide.subtitle}
          </Text>
          <Text at={box(1.1, 6.45, 10.6, 0.4)} size={12} color={DECK.onDarkMuted}>
            {slide.meta}
          </Text>
        </>
      );

    case "executive_summary":
      return (
        <>
          <Eyebrow text="Executive summary" />
          <Text at={box(MARGIN, 0.85, CONTENT_W, 1.45)} size={26} color={DECK.ink} bold leading={1.05}>
            {slide.headline}
          </Text>
          {columns(Math.max(slide.takeaways.length, 1)).map(([x, w], i) => {
            const item = slide.takeaways[i];
            if (!item) return null;
            return (
              <div key={i}>
                <Card x={x} y={2.6} w={w} h={3.75} />
                <Text at={box(x + 0.3, 2.9, w - 0.6, 0.4)} size={14} color={DECK.accent} bold>
                  {String(i + 1).padStart(2, "0")}
                </Text>
                <Text at={box(x + 0.3, 3.4, w - 0.6, 0.9)} size={19} color={DECK.ink} bold leading={1.05}>
                  {item.title}
                </Text>
                <Text at={box(x + 0.3, 4.35, w - 0.6, 1.8)} size={14} color={DECK.muted} leading={1.15}>
                  {item.text}
                </Text>
              </div>
            );
          })}
        </>
      );

    case "kpi_cards":
      return (
        <>
          <Header title={slide.title} eyebrow="Key metrics" />
          {slide.kpis.length === 0 && (
            <Text at={box(MARGIN, 2.4, CONTENT_W, 1)} size={18} color={DECK.muted}>
              No metrics available.
            </Text>
          )}
          {columns(Math.max(slide.kpis.length, 1)).map(([x, w], i) => {
            const kpi = slide.kpis[i];
            if (!kpi) return null;
            const size = (slide.kpis.length <= 3 ? 48 : 42) - (kpi.value.length > 7 ? 8 : 0);
            return (
              <div key={i}>
                <Card x={x} y={2.35} w={w} h={2.9} />
                <Rect at={box(x, 2.35, w, 0.08)} color={DECK.accent} />
                <Text at={box(x + 0.32, 2.7, w - 0.64, 0.62)} size={14} color={DECK.muted} bold leading={1}>
                  {kpi.label}
                </Text>
                <Text at={box(x + 0.32, 3.35, w - 0.64, 1.05)} size={size} color={DECK.ink} bold anchor="middle">
                  {kpi.value}
                </Text>
                <Text at={box(x + 0.32, 4.45, w - 0.64, 0.6)} size={12} color={DECK.muted}>
                  {kpi.caption}
                </Text>
              </div>
            );
          })}
        </>
      );

    case "chart_insight": {
      const top = 1.95;
      const height = 4.65;
      if (!slide.chart) {
        return (
          <>
            <Header title={slide.title} eyebrow="Insight" />
            <BulletCards bullets={slide.bullets} x={MARGIN} y={top} w={CONTENT_W} h={height} horizontal />
          </>
        );
      }
      const chartW = 7.55;
      const sideX = MARGIN + chartW + GUTTER;
      return (
        <>
          <Header title={slide.title} eyebrow="Insight" />
          <Card x={MARGIN} y={top} w={chartW} h={height} />
          <Text at={box(MARGIN + 0.3, top + 0.22, chartW - 0.6, 0.4)} size={13} color={DECK.muted} bold>
            {slide.chart.caption}
          </Text>
          <div style={box(MARGIN + 0.35, top + 0.8, chartW - 0.7, height - 1.05)}>
            <ChartView chart={slide.chart} />
          </div>
          <BulletCards
            bullets={slide.bullets}
            x={sideX}
            y={top}
            w={SLIDE_WIDTH_IN - MARGIN - sideX}
            h={height}
            horizontal={false}
          />
        </>
      );
    }

    case "hypotheses":
      return (
        <>
          <Header title={slide.title} eyebrow="Hypotheses to test" />
          {columns(Math.max(slide.items.length, 1)).map(([x, w], i) => {
            const h = slide.items[i];
            if (!h) return null;
            const pill = {
              high: { bg: DECK.accent, fg: "#FFFFFF" },
              medium: { bg: DECK.accentSoft, fg: DECK.accent },
              low: { bg: "#EEEEF1", fg: DECK.muted },
            }[h.confidence];
            return (
              <div key={i}>
                <Card x={x} y={1.95} w={w} h={4.65} />
                <div
                  style={{
                    ...box(x + 0.3, 2.25, 1.75, 0.36),
                    background: pill.bg,
                    color: pill.fg,
                    borderRadius: u(0.18),
                    fontSize: pt(11),
                    fontWeight: 700,
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  {h.confidence[0].toUpperCase() + h.confidence.slice(1)} confidence
                </div>
                <Text at={box(x + 0.3, 2.9, w - 0.6, 1.9)} size={17} color={DECK.ink} bold leading={1.08}>
                  {h.statement}
                </Text>
                <Rect at={box(x + 0.3, 4.9, w - 0.6, 0.01)} color={DECK.cardBorder} />
                <Text at={box(x + 0.3, 5.05, w - 0.6, 0.3)} size={10} color={DECK.muted} bold>
                  HOW TO TEST
                </Text>
                <Text at={box(x + 0.3, 5.35, w - 0.6, 1.1)} size={13} color={DECK.muted}>
                  {h.test}
                </Text>
              </div>
            );
          })}
        </>
      );

    case "next_steps":
      return (
        <>
          <Rect at={box(1.1, 0.85, 1.1, 0.07)} color={DECK.accentOnDark} />
          <Text at={box(1.1, 1.05, 11.2, 1.3)} size={32} color={DECK.onDark} bold leading={1}>
            {slide.title}
          </Text>
          {slide.steps.map((step, i) => {
            const y = 2.6 + i * 1.1;
            return (
              <div key={i}>
                <div
                  style={{
                    ...box(1.1, y, 0.62, 0.62),
                    background: DECK.accent,
                    borderRadius: "50%",
                    color: DECK.onDark,
                    fontSize: pt(18),
                    fontWeight: 700,
                    display: "grid",
                    placeItems: "center",
                  }}
                >
                  {i + 1}
                </div>
                <Text at={box(2.05, y - 0.05, 10, 0.75)} size={20} color={DECK.onDark} anchor="middle">
                  {step}
                </Text>
              </div>
            );
          })}
        </>
      );
  }
}

function Header({ title, eyebrow }: { title: string; eyebrow: string }) {
  return (
    <>
      <Eyebrow text={eyebrow} />
      <Text at={box(MARGIN, 0.78, CONTENT_W, 1.05)} size={28} color={DECK.ink} bold leading={1}>
        {title}
      </Text>
    </>
  );
}

function Eyebrow({ text }: { text: string }) {
  return (
    <>
      <Rect at={box(MARGIN, 0.5, 0.35, 0.06)} color={DECK.accent} />
      <Text at={box(MARGIN + 0.5, 0.36, 6, 0.35)} size={11} color={DECK.accent} bold>
        {text.toUpperCase()}
      </Text>
    </>
  );
}

function Card({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  return <Rect at={box(x, y, w, h)} color={DECK.card} radius={0.12} border={DECK.cardBorder} />;
}

function BulletCards({
  bullets,
  x,
  y,
  w,
  h,
  horizontal,
}: {
  bullets: string[];
  x: number;
  y: number;
  w: number;
  h: number;
  horizontal: boolean;
}) {
  const n = bullets.length;
  if (!n) return null;
  return (
    <>
      {bullets.map((text, i) => {
        const cw = horizontal ? (w - GUTTER * (n - 1)) / n : w;
        const ch = horizontal ? h : (h - GUTTER * (n - 1)) / n;
        const cx = horizontal ? x + i * (cw + GUTTER) : x;
        const cy = horizontal ? y : y + i * (ch + GUTTER);
        return (
          <div key={i}>
            <Card x={cx} y={cy} w={cw} h={ch} />
            <Rect at={box(cx, cy + 0.25, 0.07, Math.min(ch - 0.5, 0.9))} color={DECK.accent} />
            <Text
              at={box(cx + 0.3, cy + 0.2, cw - 0.55, ch - 0.4)}
              size={horizontal ? 15 : 13}
              color={DECK.ink}
              leading={1.12}
            >
              {text}
            </Text>
          </div>
        );
      })}
    </>
  );
}

export function formatChartValue(value: number, kind: Chart["value_format"]): string {
  if (kind === "percent") return `${Number(value.toFixed(1))}%`;
  if (kind === "correlation") return value.toFixed(2);
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(value / 1e3).toFixed(1)}K`;
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  if (abs >= 100) return Math.round(value).toLocaleString("en-US");
  if (abs >= 1) return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return String(Number(value.toPrecision(3)));
}

function barColor(chart: Chart, value: number) {
  if (chart.kind !== "correlations") return DECK.accent;
  return value >= 0 ? DECK.positive : DECK.negative;
}

function ChartView({ chart }: { chart: Chart }) {
  const labelStyle: CSSProperties = { fontSize: pt(12), color: DECK.muted, lineHeight: 1.2 };
  const valueStyle: CSSProperties = { fontSize: pt(12), color: DECK.ink, fontWeight: 700 };

  if (chart.kind === "numeric_summary") {
    const max = Math.max(...chart.values, 0) || 1;
    return (
      <div className="flex h-full items-end" style={{ gap: u(0.3) }}>
        {chart.categories.map((c, i) => (
          <div key={c} className="flex h-full flex-1 flex-col items-center justify-end" style={{ gap: u(0.06) }}>
            <span style={valueStyle}>{formatChartValue(chart.values[i], chart.value_format)}</span>
            <div
              style={{
                width: "100%",
                height: `${(Math.max(chart.values[i], 0) / max) * 78}%`,
                minHeight: 2,
                background: barColor(chart, chart.values[i]),
                borderRadius: `${u(0.05)} ${u(0.05)} 0 0`,
              }}
            />
            <span style={labelStyle}>{c}</span>
          </div>
        ))}
      </div>
    );
  }

  // Correlations get a diverging axis only when both signs are present; r is
  // always drawn against its full 0..1 range so bar length stays honest.
  const isCorrelation = chart.kind === "correlations";
  const signed = isCorrelation && chart.values.some((v) => v < 0);
  const max = isCorrelation ? 1 : Math.max(...chart.values.map(Math.abs), 0) || 1;
  return (
    <div className="flex h-full flex-col justify-center" style={{ gap: u(0.18) }}>
      {chart.categories.map((c, i) => {
        const value = chart.values[i];
        const pct = (Math.abs(value) / max) * (signed ? 50 : 82);
        return (
          <div key={c} className="grid items-center" style={{ gridTemplateColumns: "34% 1fr", gap: u(0.15) }}>
            <span className="truncate text-right" style={labelStyle} title={c}>
              {c}
            </span>
            <div className="relative flex items-center" style={{ height: u(0.34) }}>
              <div
                style={{
                  position: "absolute",
                  height: "100%",
                  width: `${pct}%`,
                  left: signed ? (value >= 0 ? "50%" : `${50 - pct}%`) : 0,
                  background: barColor(chart, value),
                  borderRadius: u(0.04),
                }}
              />
              <span
                style={{
                  ...valueStyle,
                  position: "absolute",
                  left: signed
                    ? value >= 0
                      ? `calc(50% + ${pct}% + ${u(0.08)})`
                      : undefined
                    : `calc(${pct}% + ${u(0.08)})`,
                  right: signed && value < 0 ? `calc(50% + ${pct}% + ${u(0.08)})` : undefined,
                }}
              >
                {formatChartValue(value, chart.value_format)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
