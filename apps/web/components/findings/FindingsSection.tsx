import { Info, Search } from "lucide-react";

import type { Finding } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { MiniChart } from "./MiniChart";

// Effect strength is ordinal, not a status: one neutral ramp, always with a text label.
const STRENGTH: Record<Finding["effect"]["strength"], { label: string; className: string }> = {
  strong: { label: "Strong effect", className: "bg-accent text-accent-foreground" },
  moderate: { label: "Moderate effect", className: "bg-accent-soft text-accent" },
  weak: { label: "Weak effect", className: "bg-surface-muted text-muted" },
  negligible: { label: "Negligible", className: "bg-surface-muted text-muted" },
};

export function FindingsSection({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return (
      <section aria-labelledby="findings-heading" className="space-y-2">
        <h2 id="findings-heading" className="text-lg font-semibold tracking-tight">
          Findings
        </h2>
        <p className="text-sm text-muted">
          No statistically significant patterns were found. Try a larger dataset or set the
          outcome column explicitly.
        </p>
      </section>
    );
  }
  const followUps = findings.filter((f) => f.source === "follow_up").length;
  return (
    <section aria-labelledby="findings-heading" className="space-y-4">
      <div>
        <h2 id="findings-heading" className="text-lg font-semibold tracking-tight">
          Findings
        </h2>
        <p className="text-sm text-muted">
          Tested patterns ranked by effect size and significance
          {followUps > 0 && `, including ${followUps} follow-up ${followUps === 1 ? "analysis" : "analyses"} by Claude`}
          . Significance is FDR-adjusted across every test run.
        </p>
      </div>
      <ol className="grid gap-4 lg:grid-cols-2">
        {findings.map((f) => (
          <li key={f.id} id={`finding-${f.id}`} className="scroll-mt-20">
            <FindingCard finding={f} />
          </li>
        ))}
      </ol>
    </section>
  );
}

export function FindingCard({ finding: f }: { finding: Finding }) {
  const strength = STRENGTH[f.effect.strength];
  const p = f.q_value ?? f.p_value;
  return (
    <article className="h-full min-w-0 rounded-2xl border border-border bg-surface p-5 target:ring-2 target:ring-accent">
      <header className="flex flex-wrap items-start gap-2">
        <span className="rounded-md bg-surface-muted px-1.5 py-0.5 font-mono text-xs text-muted">{f.id}</span>
        <h3 className="min-w-0 flex-1 font-medium">{f.title}</h3>
        <span className="text-lg font-semibold tabular-nums tracking-tight">{f.headline}</span>
      </header>
      <p className="mt-2 text-sm text-muted">{f.summary}</p>
      <div className="mt-4">
        <MiniChart chart={f.chart} label={f.title} />
      </div>
      <footer className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className={cn("rounded-full px-2 py-0.5 font-medium", strength.className)}>{strength.label}</span>
        <span title={`${f.effect.name} = ${f.effect.value}`}>
          {f.effect.name} {Number(f.effect.value.toPrecision(3))}
        </span>
        <span>n = {f.n.toLocaleString("en-US")}</span>
        {p != null && (
          <span title={f.q_value != null ? "FDR-adjusted q-value" : "p-value (follow-ups are not FDR-adjusted)"}>
            {f.q_value != null ? "q" : "p"} {formatP(p)}
          </span>
        )}
        {f.source === "follow_up" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">
            <Search className="size-3" aria-hidden /> Claude follow-up
          </span>
        )}
        {f.filter && <span className="rounded-full bg-surface-muted px-2 py-0.5">Subset: {f.filter}</span>}
      </footer>
      {f.caveats.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-border pt-3 text-xs text-muted">
          {f.caveats.map((c) => (
            <li key={c} className="flex gap-1.5">
              <Info className="mt-0.5 size-3 shrink-0" aria-hidden />
              {c}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function formatP(p: number): string {
  if (p < 0.001) return "< 0.001";
  return p.toFixed(3);
}
