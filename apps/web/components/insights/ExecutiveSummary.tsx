import { Sparkles } from "lucide-react";

import type { Insights } from "@/lib/api/types";

export function ExecutiveSummary({ insights }: { insights: Insights }) {
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-accent/25 bg-accent-soft p-5 sm:p-6">
        <p className="flex items-center gap-2 text-sm font-medium text-accent">
          <Sparkles className="size-4" aria-hidden />
          Executive summary
        </p>
        <p className="mt-2 leading-relaxed">{insights.executive_summary}</p>
      </section>

      <div className="grid gap-3 sm:grid-cols-2">
        {insights.key_findings.map((f) => (
          <article key={f.title} className="min-w-0 rounded-xl border border-border bg-surface p-4">
            <h4 className="font-medium">{f.title}</h4>
            <p className="mt-1 text-sm text-muted">{f.detail}</p>
            {f.supporting_stats.length > 0 && (
              <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Supporting statistics">
                {f.supporting_stats.map((s) => (
                  <li
                    key={s}
                    className="rounded-md bg-surface-muted px-2 py-0.5 font-mono text-xs text-muted"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
