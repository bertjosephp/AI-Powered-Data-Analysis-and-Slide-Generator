import { Card } from "@/components/ui/Card";
import type { ColumnProfile } from "@/lib/api/types";
import { formatNumber } from "@/lib/utils";

export function ColumnTable({ columns }: { columns: ColumnProfile[] }) {
  return (
    <Card title="Columns" description={`${columns.length} profiled`}>
      <div className="-mx-5 overflow-x-auto sm:-mx-6">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="text-left text-muted">
            <tr className="border-b border-border">
              <th className="px-5 py-2 font-medium sm:pl-6">Column</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 text-right font-medium">Missing</th>
              <th className="px-3 py-2 text-right font-medium">Unique</th>
              <th className="px-5 py-2 font-medium sm:pr-6">Summary</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr key={c.name} className="border-b border-border last:border-0">
                <td className="max-w-48 truncate px-5 py-2.5 font-medium sm:pl-6" title={c.name}>
                  {c.name}
                </td>
                <td className="px-3 py-2.5">
                  <span className="rounded-md bg-surface-muted px-2 py-0.5 text-xs text-muted">
                    {c.inferred_type}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {c.missing_count ? `${formatNumber(c.missing_pct)}%` : "—"}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {formatNumber(c.unique_count)}
                </td>
                <td className="px-5 py-2.5 text-muted sm:pr-6">{summarize(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function summarize(c: ColumnProfile): string {
  switch (c.inferred_type) {
    case "numeric":
      return `mean ${formatNumber(c.mean)} · median ${formatNumber(c.median)} · ${formatNumber(
        c.min,
      )} to ${formatNumber(c.max)}`;
    case "datetime":
      return c.min_date && c.max_date
        ? `${c.min_date.slice(0, 10)} to ${c.max_date.slice(0, 10)}`
        : "—";
    case "categorical":
    case "boolean": {
      const top = c.top_values?.slice(0, 3) ?? [];
      return top.length ? top.map((t) => `${t.value} (${formatNumber(t.count)})`).join(", ") : "—";
    }
    case "id":
      return "Identifier, excluded from analysis";
    default:
      return "Free text";
  }
}
