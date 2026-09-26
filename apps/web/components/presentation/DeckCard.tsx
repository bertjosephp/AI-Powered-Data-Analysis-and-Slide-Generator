import { Download, ExternalLink, Info, Loader2, Presentation as PresentationIcon } from "lucide-react";

import type { JobState } from "@/lib/api/types";

export function DeckCard({ job }: { job: JobState }) {
  const deckStage = job.stages.find((s) => s.key === "generate_deck");
  const presentation = job.presentation;

  if (deckStage?.status === "running") {
    return (
      <section className="flex items-center gap-4 rounded-2xl border border-border bg-surface p-5 sm:p-6">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
          <Loader2 className="size-5 animate-spin" aria-hidden />
        </span>
        <div>
          <h2 className="font-semibold">Building your deck in Gamma…</h2>
          <p className="text-sm text-muted">
            This usually takes 1–3 minutes. You can read the insights below meanwhile.
          </p>
        </div>
      </section>
    );
  }

  if (presentation?.status !== "completed" || !presentation.gamma_url) return null;

  const format = job.options.export_as?.toUpperCase();
  return (
    <section className="rounded-2xl border border-success/30 bg-success-soft p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-success text-white">
          <PresentationIcon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">Your deck is ready</h2>
          <p className="text-sm text-muted">
            {job.insights?.slide_outline.length ?? job.options.num_slides} slides generated with
            Gamma
          </p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          <a
            href={presentation.gamma_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 sm:flex-none"
          >
            Open in Gamma <ExternalLink className="size-4" aria-hidden />
          </a>
          {presentation.export_url && (
            <a
              href={presentation.export_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-muted sm:flex-none"
            >
              <Download className="size-4" aria-hidden /> Download {format}
            </a>
          )}
        </div>
      </div>
      {presentation.mock && (
        <p className="mt-4 flex items-start gap-2 text-sm text-muted">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
          Mock mode: this link is a placeholder. Set MOCK_EXTERNAL=false with API keys to generate
          a real deck.
        </p>
      )}
      {job.insights && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-muted hover:text-foreground">
            Slide outline sent to Gamma
          </summary>
          <ol className="mt-3 grid gap-2 sm:grid-cols-2">
            {job.insights.slide_outline.map((slide, i) => (
              <li key={`${i}-${slide.title}`} className="rounded-lg bg-surface p-3">
                <p className="font-medium">
                  {i + 1}. {slide.title}
                </p>
                <ul className="mt-1 list-disc pl-5 text-muted">
                  {slide.bullets.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
