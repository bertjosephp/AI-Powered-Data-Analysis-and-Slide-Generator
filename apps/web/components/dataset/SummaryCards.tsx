import { AlertTriangle } from "lucide-react";

import type { DatasetProfile } from "@/lib/api/types";
import { formatBytes, formatNumber } from "@/lib/utils";

const TYPE_ORDER = ["numeric", "categorical", "datetime", "boolean", "text", "id"] as const;

export function SummaryCards({ profile }: { profile: DatasetProfile }) {
  const typeCounts = TYPE_ORDER.map((t) => ({
    type: t,
    count: profile.columns.filter((c) => c.inferred_type === t).length,
  })).filter((t) => t.count > 0);

  const tiles = [
    {
      label: "Rows",
      value: formatNumber(profile.n_rows, { compact: true }),
      note: profile.sampled
        ? `Stats from a ${formatNumber(profile.sample_rows, { compact: true })}-row sample`
        : formatBytes(profile.memory_bytes) + " in memory",
    },
    {
      label: "Columns",
      value: formatNumber(profile.n_cols),
      note: typeCounts.map((t) => `${t.count} ${t.type}`).join(" · "),
    },
    {
      label: "Missing cells",
      value: `${formatNumber(profile.missing_pct_total)}%`,
      note: `${formatNumber(profile.missing_cells_total)} of ${formatNumber(
        profile.n_rows * profile.n_cols,
        { compact: true },
      )} cells`,
    },
    {
      label: "Duplicate rows",
      value: formatNumber(profile.duplicate_rows),
      note: profile.duplicate_rows ? "Fully identical rows" : "None found",
    },
  ];

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="min-w-0 rounded-2xl border border-border bg-surface p-4 shadow-card">
            <dt className="text-sm text-muted">{tile.label}</dt>
            <dd className="mt-1 text-2xl font-semibold tracking-tight">{tile.value}</dd>
            <dd className="mt-1 text-xs text-muted">{tile.note}</dd>
          </div>
        ))}
      </dl>

      {profile.warnings.length > 0 && (
        <div className="rounded-xl border border-warning/30 bg-warning-soft p-4">
          <p className="flex items-center gap-2 text-sm font-medium text-warning">
            <AlertTriangle className="size-4" aria-hidden />
            Data quality warnings
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-6 text-sm">
            {profile.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
