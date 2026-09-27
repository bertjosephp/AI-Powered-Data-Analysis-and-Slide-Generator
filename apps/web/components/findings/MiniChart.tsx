// Small single-series charts for finding cards: labeled bars (with the overall
// value as a reference rule) and a line for trends. Single hue from the viz
// tokens; every value is directly labeled or exposed as a tooltip.
import type { Finding } from "@/lib/api/types";

type ChartData = Finding["chart"];

export function formatValue(value: number, format: ChartData["value_format"]): string {
  if (format === "percent") return `${Number(value.toFixed(1))}%`;
  if (format === "correlation") return value.toFixed(2);
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(value / 1e3).toFixed(1)}K`;
  if (abs >= 100) return Math.round(value).toLocaleString("en-US");
  return Number(value.toPrecision(3)).toLocaleString("en-US");
}

export function MiniChart({ chart, label }: { chart: ChartData; label: string }) {
  return chart.kind === "line" ? (
    <LineChart chart={chart} label={label} />
  ) : (
    <BarList chart={chart} label={label} />
  );
}

function BarList({ chart, label }: { chart: ChartData; label: string }) {
  const max = Math.max(...chart.values.map(Math.abs), chart.reference ?? 0, 1e-9);
  const refPct = chart.reference != null ? (Math.abs(chart.reference) / max) * 100 : null;
  const rows = chart.categories.slice(0, 8);
  return (
    <figure className="space-y-1.5" aria-label={label}>
      {rows.map((category, i) => {
        const value = chart.values[i];
        const count = chart.counts?.[i];
        return (
          <div
            key={`${category}-${i}`}
            className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-2 text-xs"
            title={`${category}: ${formatValue(value, chart.value_format)}${count != null ? ` (n=${count.toLocaleString("en-US")})` : ""}`}
          >
            <span className="truncate text-muted">{category}</span>
            <span className="relative h-2 rounded-full bg-[var(--viz-track)]">
              <span
                className="absolute inset-y-0 left-0 rounded-full bg-[var(--viz-bar)]"
                style={{ width: `${Math.max((Math.abs(value) / max) * 100, 1.5)}%` }}
              />
              {refPct != null && (
                <span
                  aria-hidden
                  className="absolute -inset-y-1 w-0.5 rounded bg-foreground/60"
                  style={{ left: `${refPct}%` }}
                />
              )}
            </span>
            <span className="text-right tabular-nums">{formatValue(value, chart.value_format)}</span>
          </div>
        );
      })}
      {chart.categories.length > rows.length && (
        <p className="text-xs text-muted">+{chart.categories.length - rows.length} more</p>
      )}
      {chart.reference != null && (
        <figcaption className="flex items-center gap-1.5 pt-0.5 text-xs text-muted">
          <span aria-hidden className="inline-block h-3 w-0.5 rounded bg-foreground/60" />
          {chart.reference_label ?? "overall"}: {formatValue(chart.reference, chart.value_format)}
        </figcaption>
      )}
    </figure>
  );
}

function LineChart({ chart, label }: { chart: ChartData; label: string }) {
  const values = chart.values;
  const w = 320;
  const h = 96;
  const pad = 6;
  const lo = Math.min(...values, 0);
  const hi = Math.max(...values);
  const x = (i: number) => pad + (i / Math.max(values.length - 1, 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad);
  const peak = values.indexOf(hi);
  const last = values.length - 1;
  return (
    <figure aria-label={label}>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-24 w-full overflow-visible" role="img">
        <title>{label}</title>
        {chart.reference != null && (
          <line
            x1={pad}
            x2={w - pad}
            y1={y(chart.reference)}
            y2={y(chart.reference)}
            className="stroke-border"
            strokeWidth={1}
          />
        )}
        <polyline
          points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
          fill="none"
          stroke="var(--viz-bar)"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {values.map((v, i) => (
          <circle key={i} cx={x(i)} cy={y(v)} r={i === peak || i === last ? 3.5 : 0} fill="var(--viz-bar)">
            <title>{`${chart.categories[i]}: ${formatValue(v, chart.value_format)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-muted">
        <span>{chart.categories[0]}</span>
        <span>
          Peak {chart.categories[peak]}: {formatValue(hi, chart.value_format)}
        </span>
        <span>{chart.categories[last]}</span>
      </figcaption>
    </figure>
  );
}
