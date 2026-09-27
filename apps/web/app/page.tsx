import { BarChart3, Lock, Presentation, Sparkles } from "lucide-react";

import { UploadForm } from "@/components/upload/UploadForm";

const STEPS = [
  {
    icon: BarChart3,
    title: "Test",
    body: "Segments, drivers, thresholds and trends are tested statistically, with effect sizes and false-discovery control.",
  },
  {
    icon: Sparkles,
    title: "Explain",
    body: "Claude digs into the strongest findings with follow-up analyses and answers your question, citing the evidence.",
  },
  {
    icon: Presentation,
    title: "Present",
    body: "The story becomes an editable PowerPoint deck with native charts, every figure computed from your data.",
  },
];

export default function HomePage() {
  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] lg:gap-14 xl:gap-20">
      <section className="lg:sticky lg:top-24">
        <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted shadow-card">
          <span className="size-1.5 rounded-full bg-accent" aria-hidden />
          Statistically tested · Explained by Claude
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
          From spreadsheet to{" "}
          <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
            boardroom-ready insight
          </span>
        </h1>
        <p className="mt-4 max-w-xl text-lg text-pretty text-muted">
          Upload a dataset, ask what you want to know, and get tested findings, clear answers and a
          polished slide deck, not a table of means and medians.
        </p>

        <ol className="mt-10 space-y-5">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="flex gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-border bg-surface text-accent shadow-card">
                <Icon className="size-5" aria-hidden />
              </span>
              <div>
                <p className="font-medium">
                  <span className="text-muted">{String(i + 1).padStart(2, "0")}</span> {title}
                </p>
                <p className="mt-0.5 max-w-md text-sm text-muted">{body}</p>
              </div>
            </li>
          ))}
        </ol>

        <p className="mt-10 flex items-center gap-2 text-sm text-muted">
          <Lock className="size-4" aria-hidden />
          Claude sees statistics, never your rows.
        </p>
      </section>

      <UploadForm />
    </div>
  );
}
