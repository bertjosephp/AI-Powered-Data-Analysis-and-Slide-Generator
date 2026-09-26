import { Check, Loader2, X } from "lucide-react";

import type { Stage } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const HINTS: Partial<Record<Stage["key"], string>> = {
  analyze: "Usually under a minute",
  generate_deck: "Usually 1–3 minutes",
};

const STATUS_TEXT: Record<Stage["status"], string> = {
  pending: "Waiting",
  running: "In progress",
  done: "Done",
  failed: "Failed",
};

export function PipelineTracker({ stages }: { stages: Stage[] }) {
  return (
    <ol aria-label="Pipeline progress" className="grid gap-3 sm:grid-cols-4 sm:gap-0">
      {stages.map((stage, i) => (
        <li
          key={stage.key}
          aria-current={stage.status === "running" ? "step" : undefined}
          className="relative flex gap-3 sm:flex-col sm:items-center sm:text-center"
        >
          {i > 0 && (
            <span
              aria-hidden
              className={cn(
                "absolute top-4 right-1/2 -left-1/2 hidden h-0.5 sm:block",
                stages[i - 1].status === "done" ? "bg-success" : "bg-border",
              )}
            />
          )}
          <StageIcon status={stage.status} index={i} />
          <div className="min-w-0 sm:mt-2 sm:px-2">
            <p
              className={cn(
                "text-sm font-medium",
                stage.status === "pending" && "text-muted",
                stage.status === "failed" && "text-danger",
              )}
            >
              {stage.label}
            </p>
            <p className="text-xs text-muted">
              <span className="sr-only">Status: </span>
              {stage.status === "running" && HINTS[stage.key]
                ? `${STATUS_TEXT.running} · ${HINTS[stage.key]}`
                : STATUS_TEXT[stage.status]}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function StageIcon({ status, index }: { status: Stage["status"]; index: number }) {
  const base = "relative z-10 grid size-8 shrink-0 place-items-center rounded-full text-sm";
  switch (status) {
    case "done":
      return (
        <span className={cn(base, "bg-success text-white")}>
          <Check className="size-4" aria-hidden />
        </span>
      );
    case "running":
      return (
        <span className={cn(base, "bg-accent-soft text-accent ring-2 ring-accent")}>
          <Loader2 className="size-4 animate-spin" aria-hidden />
        </span>
      );
    case "failed":
      return (
        <span className={cn(base, "bg-danger text-white")}>
          <X className="size-4" aria-hidden />
        </span>
      );
    default:
      return (
        <span className={cn(base, "border border-border bg-surface text-muted")}>{index + 1}</span>
      );
  }
}
