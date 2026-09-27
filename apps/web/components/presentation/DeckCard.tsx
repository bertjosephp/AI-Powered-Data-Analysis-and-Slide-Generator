import { Download, Loader2, Presentation as PresentationIcon } from "lucide-react";

import { API_BASE_URL } from "@/lib/api/client";
import type { JobState } from "@/lib/api/types";
import { formatBytes } from "@/lib/utils";

export function DeckCard({ job }: { job: JobState }) {
  const deckStage = job.stages.find((s) => s.key === "generate_deck");
  const presentation = job.presentation;

  if (deckStage?.status === "running") {
    return (
      <section className="flex items-center gap-3 rounded-2xl border border-border bg-surface p-4 shadow-card">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
          <Loader2 className="size-5 animate-spin" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Building your slide deck…</h2>
          <p className="text-xs text-muted">Placing the charts and figures from your data.</p>
        </div>
      </section>
    );
  }

  if (!presentation) return null;

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card">
      <div className="flex items-center gap-3 bg-gradient-to-br from-indigo-600 to-violet-600 p-4 text-white">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/15">
          <PresentationIcon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Your deck is ready</h2>
          <p className="text-xs text-white/80">
            {presentation.slide_count} slides · editable PowerPoint · {formatBytes(presentation.size_bytes)}
          </p>
        </div>
      </div>
      <div className="p-3">
        <a
          href={`${API_BASE_URL}${presentation.download_path}`}
          download
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background transition hover:opacity-90"
        >
          <Download className="size-4" aria-hidden /> Download .pptx
        </a>
      </div>
    </section>
  );
}
