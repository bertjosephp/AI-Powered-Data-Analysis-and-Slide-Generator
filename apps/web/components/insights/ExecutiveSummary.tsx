import { AlertTriangle, CheckCircle2, Sparkles } from "lucide-react";

import { FindingChips } from "@/components/findings/FindingChip";
import type { Grounding, Insights } from "@/lib/api/types";

type Props = {
  insights: Insights;
  grounding?: Grounding | null;
  titles: Map<string, string>;
};

export function ExecutiveSummary({ insights, grounding, titles }: Props) {
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-medium text-accent">
            <Sparkles className="size-4" aria-hidden />
            Executive summary
          </p>
          {grounding && <GroundingBadge grounding={grounding} />}
        </div>
        <p className="mt-2 leading-relaxed">{insights.executive_summary}</p>
        {grounding && grounding.unverified.length > 0 && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-muted hover:text-foreground">
              Figures not found in the computed evidence
            </summary>
            <ul className="mt-2 space-y-1 text-muted">
              {grounding.unverified.map((u) => (
                <li key={`${u.location}-${u.value}`}>
                  <span className="font-medium text-foreground">{u.value}</span> in {u.location}:{" "}
                  <q>{u.context}</q>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <div className="grid gap-3 sm:grid-cols-2">
        {insights.key_findings.map((f) => (
          <article key={f.title} className="min-w-0 rounded-xl border border-border bg-surface p-4">
            <h4 className="font-medium">{f.title}</h4>
            <p className="mt-1 text-sm text-muted">{f.detail}</p>
            <div className="mt-3">
              <FindingChips ids={f.finding_ids} titles={titles} />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function GroundingBadge({ grounding }: { grounding: Grounding }) {
  const unverified = grounding.unverified.length;
  if (grounding.checked === 0) return null;
  return unverified === 0 ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
      <CheckCircle2 className="size-3.5" aria-hidden />
      All {grounding.checked} figures traced to the analysis
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2.5 py-0.5 text-xs font-medium text-warning">
      <AlertTriangle className="size-3.5" aria-hidden />
      {unverified} of {grounding.checked} figures unverified
    </span>
  );
}
