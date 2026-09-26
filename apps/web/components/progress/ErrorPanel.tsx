"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";

import { ApiError, retryJob } from "@/lib/api/client";
import type { JobState } from "@/lib/api/types";
import { jobQueryKey } from "@/lib/hooks/useJobPolling";

const HINTS: Record<string, string> = {
  LLM_ERROR: "Claude couldn't complete the analysis. Check the Anthropic API key, then retry.",
  LLM_SCHEMA_ERROR: "Claude's answer wasn't in the expected format. Retrying usually fixes this.",
  GAMMA_ERROR: "Gamma couldn't build the deck. Check the Gamma API key and credits, then retry.",
  GAMMA_TIMEOUT:
    "Gamma is taking longer than usual. Retrying keeps waiting on the same deck, so it won't use extra credits.",
  INTERNAL_ERROR: "Something unexpected went wrong on the server.",
};

export function ErrorPanel({ job }: { job: JobState }) {
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: () => retryJob(job.job_id),
    // The job is no longer terminal, so refetching restarts polling.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobQueryKey(job.job_id) }),
  });

  if (!job.error) return null;
  const stageLabel = job.stages.find((s) => s.key === job.error?.stage)?.label;
  // The dataset is only kept until it's profiled; before that, a retry has nothing to run on.
  const retryable = job.profile != null;

  return (
    <section
      role="alert"
      className="rounded-2xl border border-danger/30 bg-danger-soft p-5 sm:p-6"
    >
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-danger">
            {stageLabel ? `${stageLabel} failed` : "The analysis failed"}
          </h2>
          <p className="mt-1 text-sm">{job.error.message}</p>
          {HINTS[job.error.code] && (
            <p className="mt-2 text-sm text-muted">{HINTS[job.error.code]}</p>
          )}
          {retry.error && (
            <p className="mt-2 text-sm text-danger">
              {retry.error instanceof ApiError ? retry.error.message : "Retry failed."}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {retryable && (
              <button
                type="button"
                onClick={() => retry.mutate()}
                disabled={retry.isPending || retry.isSuccess}
                className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:opacity-90 disabled:opacity-60"
              >
                {retry.isPending || retry.isSuccess ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <RotateCcw className="size-4" aria-hidden />
                )}
                Retry from {stageLabel?.toLowerCase() ?? "failed step"}
              </button>
            )}
            <Link
              href="/"
              className="inline-flex items-center rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-muted"
            >
              {retryable ? "Start over" : "Upload again"}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
