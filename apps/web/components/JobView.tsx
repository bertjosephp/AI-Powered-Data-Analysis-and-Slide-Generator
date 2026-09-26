"use client";

import { AlertCircle, FileSpreadsheet } from "lucide-react";
import Link from "next/link";

import { PipelineTracker } from "@/components/progress/PipelineTracker";
import { ApiError } from "@/lib/api/client";
import type { JobState } from "@/lib/api/types";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { cn } from "@/lib/utils";

type Props = { jobId: string; pollIntervalMs?: number };

export function JobView({ jobId, pollIntervalMs }: Props) {
  const { data: job, error, isPending } = useJobPolling(jobId, pollIntervalMs);

  if (isPending) return <JobSkeleton />;
  if (!job) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 text-center">
        <AlertCircle className="mx-auto size-8 text-danger" aria-hidden />
        <h1 className="mt-3 text-lg font-semibold">
          {notFound ? "Analysis not found" : "Couldn't load this analysis"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {notFound
            ? "It may have expired. Results are kept for an hour."
            : error instanceof ApiError
              ? error.message
              : "Please try again."}
        </p>
        <Link
          href="/"
          className="mt-5 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground"
        >
          Start a new analysis
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <JobHeader job={job} />
      <section className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
        <PipelineTracker stages={job.stages} />
      </section>
    </div>
  );
}

const STATUS_BADGE: Record<JobState["status"], { label: string; className: string }> = {
  queued: { label: "Queued", className: "bg-surface-muted text-muted" },
  running: { label: "Running", className: "bg-accent-soft text-accent" },
  completed: { label: "Completed", className: "bg-success-soft text-success" },
  failed: { label: "Failed", className: "bg-danger-soft text-danger" },
};

function JobHeader({ job }: { job: JobState }) {
  const badge = STATUS_BADGE[job.status];
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="grid size-10 place-items-center rounded-lg bg-accent-soft text-accent">
        <FileSpreadsheet className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-xl font-semibold tracking-tight">{job.filename}</h1>
        <p className="text-sm text-muted">
          {job.options.num_slides} slides · {job.options.tone} tone · for {job.options.audience}
        </p>
      </div>
      <span className={cn("rounded-full px-3 py-1 text-xs font-medium", badge.className)}>
        {badge.label}
      </span>
    </div>
  );
}

function JobSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-busy="true" aria-label="Loading analysis">
      <div className="flex items-center gap-3">
        <div className="size-10 rounded-lg bg-surface-muted" />
        <div className="h-6 w-56 rounded bg-surface-muted" />
      </div>
      <div className="h-28 rounded-2xl bg-surface-muted" />
      <div className="grid gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 rounded-xl bg-surface-muted" />
        ))}
      </div>
    </div>
  );
}
