"use client";

import { Loader2 } from "lucide-react";

import { useServerStatus } from "@/lib/hooks/useServerStatus";

export const SLOW_WAKE_SECONDS = 90;

/** Explains the free demo server's cold start while it wakes up. */
export function ServerWakeBanner() {
  const { state, waitedSeconds } = useServerStatus();
  if (state !== "waking") return null;
  const slow = waitedSeconds >= SLOW_WAKE_SECONDS;
  return (
    <div
      role="status"
      aria-live="polite"
      className="border-b border-accent/20 bg-accent-soft/80 backdrop-blur-md"
    >
      <div className="mx-auto flex max-w-7xl items-start gap-3 px-4 py-3 text-sm sm:px-6">
        <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-accent">
            {slow ? "Taking longer than usual, still trying…" : "Waking up the analysis server…"}
          </p>
          <p className="text-muted">
            This free demo server sleeps when idle, so the first request can take up to a minute.
            Everything will load automatically once it&apos;s up.
          </p>
        </div>
        <span
          className="shrink-0 font-mono text-xs text-muted tabular-nums"
          aria-label="Seconds waited"
        >
          {waitedSeconds}s
        </span>
      </div>
      <div className="h-0.5 overflow-hidden bg-accent/10" aria-hidden>
        <div className="h-full w-1/3 animate-[wake_1.6s_ease-in-out_infinite] bg-accent motion-reduce:animate-none" />
      </div>
    </div>
  );
}
