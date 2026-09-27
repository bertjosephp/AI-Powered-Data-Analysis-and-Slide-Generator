import { FlaskConical } from "lucide-react";

import { FindingChips } from "@/components/findings/FindingChip";
import { Card } from "@/components/ui/Card";
import type { Insights } from "@/lib/api/types";
import { cn } from "@/lib/utils";

// Confidence is ordinal, not a status: one neutral ramp, always with a text label.
const CONFIDENCE = {
  low: { label: "Low confidence", className: "bg-surface-muted text-muted" },
  medium: { label: "Medium confidence", className: "bg-accent-soft text-accent" },
  high: { label: "High confidence", className: "bg-accent text-accent-foreground" },
};

export function HypothesesList({
  hypotheses,
  titles,
}: {
  hypotheses: Insights["hypotheses"];
  titles: Map<string, string>;
}) {
  return (
    <Card title="Hypotheses to test" description="Grounded in the findings; not yet proven">
      <ul className="space-y-4">
        {hypotheses.map((h) => (
          <li key={h.statement} className="border-b border-border pb-4 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="font-medium">{h.statement}</p>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium",
                  CONFIDENCE[h.confidence].className,
                )}
              >
                {CONFIDENCE[h.confidence].label}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted">{h.rationale}</p>
            <p className="mt-2 flex gap-2 text-sm">
              <FlaskConical className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <span>
                <span className="sr-only">Suggested test: </span>
                {h.test}
              </span>
            </p>
            <div className="mt-2">
              <FindingChips ids={h.finding_ids} titles={titles} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
