import { CheckCircle2 } from "lucide-react";

import { Card } from "@/components/ui/Card";
import type { ColumnProfile } from "@/lib/api/types";
import { formatNumber } from "@/lib/utils";

const MAX_BARS = 12;

export function MissingValues({ columns }: { columns: ColumnProfile[] }) {
  const withMissing = columns
    .filter((c) => c.missing_count > 0)
    .sort((a, b) => b.missing_pct - a.missing_pct);
  const shown = withMissing.slice(0, MAX_BARS);

  return (
    <Card
      title="Missing values"
      description={
        withMissing.length
          ? `${withMissing.length} of ${columns.length} columns have gaps`
          : undefined
      }
    >
      {shown.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="size-4" aria-hidden />
          No missing values in any column.
        </p>
      ) : (
        <ul className="space-y-2.5" aria-label="Percent missing by column">
          {shown.map((c) => (
            <li
              key={c.name}
              className="grid grid-cols-[minmax(0,8rem)_1fr_auto] items-center gap-3 text-sm"
            >
              <span className="truncate" title={c.name}>
                {c.name}
              </span>
              <span className="h-2 rounded-full bg-[var(--viz-track)]" aria-hidden>
                <span
                  className="block h-full rounded-full bg-[var(--viz-bar)]"
                  style={{ width: `${Math.max(c.missing_pct, 1)}%` }}
                />
              </span>
              <span className="text-right text-muted tabular-nums">
                {formatNumber(c.missing_pct)}%{" "}
                <span className="text-xs">({formatNumber(c.missing_count)})</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {withMissing.length > MAX_BARS && (
        <p className="mt-3 text-xs text-muted">
          +{withMissing.length - MAX_BARS} more columns with missing values (see the column table).
        </p>
      )}
    </Card>
  );
}
