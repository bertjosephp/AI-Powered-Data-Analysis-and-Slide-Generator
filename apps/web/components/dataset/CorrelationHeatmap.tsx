"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import type { DatasetProfile } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Correlation = NonNullable<DatasetProfile["correlation"]>;
type Pair = { a: string; b: string; r: number | null };

const LABEL_THRESHOLD = 0.5;
const STRONG = 0.6;

/** Fill for r in [-1, 1]: gray midpoint mixed toward the blue (+) or red (-) pole. */
export function cellColor(r: number | null) {
  if (r === null) return "var(--surface-muted)";
  const pole = r >= 0 ? "var(--viz-pos)" : "var(--viz-neg)";
  return `color-mix(in oklab, var(--viz-mid), ${pole} ${Math.round(Math.abs(r) * 100)}%)`;
}

export function CorrelationHeatmap({ correlation }: { correlation: Correlation | null | undefined }) {
  const [hovered, setHovered] = useState<Pair | null>(null);
  const [asTable, setAsTable] = useState(false);

  if (!correlation || correlation.columns.length < 2) {
    return (
      <Card title="Correlations">
        <p className="text-sm text-muted">
          At least two numeric columns are needed to compute correlations.
        </p>
      </Card>
    );
  }

  const { columns, matrix } = correlation;
  // Lower triangle without the diagonal: every pair once, no self-correlations.
  const rows = columns.slice(1);
  const cols = columns.slice(0, -1);
  const pairs: Pair[] = rows.flatMap((a, i) =>
    cols.slice(0, i + 1).map((b, j) => ({ a, b, r: matrix[i + 1][j] })),
  );

  return (
    <Card
      title="Correlations"
      description="Pearson r between numeric columns"
      action={
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="rounded-md border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground"
        >
          {asTable ? "Show as heatmap" : "Show as table"}
        </button>
      }
    >
      {asTable ? (
        <PairsTable pairs={pairs} />
      ) : (
        <>
          <p className="mb-3 h-5 text-sm" aria-live="polite">
            {hovered ? (
              <>
                <span className="font-medium">{hovered.a}</span> ×{" "}
                <span className="font-medium">{hovered.b}</span>: r ={" "}
                <span className="tabular-nums">{hovered.r === null ? "n/a" : hovered.r.toFixed(2)}</span>
              </>
            ) : (
              <span className="text-muted">Hover or focus a cell to read its value.</span>
            )}
          </p>
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-0.5 text-xs" onMouseLeave={() => setHovered(null)}>
              <thead>
                <tr>
                  <th />
                  {cols.map((c) => (
                    <th
                      key={c}
                      scope="col"
                      className="h-24 max-w-8 align-bottom font-normal text-muted"
                      title={c}
                    >
                      <span className="inline-block max-h-24 truncate [writing-mode:vertical-rl] rotate-180">
                        {c}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => (
                  <tr key={a}>
                    <th
                      scope="row"
                      className="max-w-32 truncate pr-2 text-right font-normal text-muted"
                      title={a}
                    >
                      {a}
                    </th>
                    {cols.map((b, j) => {
                      if (j > i) return <td key={b} />;
                      const r = matrix[i + 1][j];
                      const pair = { a, b, r };
                      return (
                        <td
                          key={b}
                          tabIndex={0}
                          aria-label={`${a} and ${b}: r = ${r === null ? "not available" : r.toFixed(2)}`}
                          onMouseEnter={() => setHovered(pair)}
                          onFocus={() => setHovered(pair)}
                          onBlur={() => setHovered(null)}
                          className={cn(
                            "size-9 min-w-9 rounded text-center tabular-nums outline-offset-1 focus-visible:outline-2 focus-visible:outline-accent",
                            r !== null && Math.abs(r) >= STRONG ? "text-white" : "text-foreground",
                            hovered?.a === a && hovered?.b === b && "ring-2 ring-foreground",
                          )}
                          style={{ background: cellColor(r) }}
                        >
                          {r === null ? "–" : Math.abs(r) >= LABEL_THRESHOLD ? r.toFixed(2) : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Legend />
        </>
      )}
    </Card>
  );
}

function Legend() {
  return (
    <div className="mt-4 max-w-xs text-xs text-muted" aria-hidden>
      <div
        className="h-2 rounded-full"
        style={{
          background:
            "linear-gradient(to right, var(--viz-neg), var(--viz-mid), var(--viz-pos))",
        }}
      />
      <div className="mt-1 flex justify-between">
        <span>−1 negative</span>
        <span>0</span>
        <span>+1 positive</span>
      </div>
    </div>
  );
}

function PairsTable({ pairs }: { pairs: Pair[] }) {
  const sorted = [...pairs].sort((x, y) => Math.abs(y.r ?? 0) - Math.abs(x.r ?? 0));
  return (
    <div className="max-h-80 overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-left text-muted">
          <tr>
            <th className="py-1.5 font-medium">Column A</th>
            <th className="py-1.5 font-medium">Column B</th>
            <th className="py-1.5 text-right font-medium">r</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={`${p.a}|${p.b}`} className="border-t border-border">
              <td className="py-1.5">{p.a}</td>
              <td className="py-1.5">{p.b}</td>
              <td className="py-1.5 text-right tabular-nums">
                {p.r === null ? "n/a" : p.r.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
