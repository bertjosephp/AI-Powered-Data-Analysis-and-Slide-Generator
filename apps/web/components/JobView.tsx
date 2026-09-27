"use client";

import { AlertCircle, FileSpreadsheet, WifiOff } from "lucide-react";
import Link from "next/link";

import { ColumnTable } from "@/components/dataset/ColumnTable";
import { CorrelationHeatmap } from "@/components/dataset/CorrelationHeatmap";
import { MissingValues } from "@/components/dataset/MissingValues";
import { SummaryCards } from "@/components/dataset/SummaryCards";
import { FindingsSection } from "@/components/findings/FindingsSection";
import { AnswersSection } from "@/components/insights/AnswersSection";
import { ExecutiveSummary } from "@/components/insights/ExecutiveSummary";
import { HypothesesList } from "@/components/insights/HypothesesList";
import { NotesList, QuestionsList } from "@/components/insights/QuestionsList";
import { DeckCard } from "@/components/presentation/DeckCard";
import { DeckPreview } from "@/components/presentation/DeckPreview";
import { ErrorPanel } from "@/components/progress/ErrorPanel";
import { PipelineTracker } from "@/components/progress/PipelineTracker";
import { ApiError } from "@/lib/api/client";
import type { JobState } from "@/lib/api/types";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import { cn } from "@/lib/utils";

type Props = { jobId: string; pollIntervalMs?: number };

export function JobView({ jobId, pollIntervalMs }: Props) {
  const { data: job, error, isPending, failureCount } = useJobPolling(jobId, pollIntervalMs);

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

  const analyzing = job.stages.some(
    (s) => (s.key === "analyze" || s.key === "explore") && s.status === "running",
  );
  const titles = new Map((job.findings ?? []).map((f) => [f.id, f.title]));
  const current = job.stages.find((s) => s.status === "running");

  return (
    <div className="space-y-8">
      <p className="sr-only" aria-live="polite">
        {job.status === "completed"
          ? "Analysis complete. Your deck is ready."
          : job.status === "failed"
            ? "The analysis failed."
            : current
              ? `${current.label}…`
              : "Queued."}
      </p>
      <div className="space-y-6">
        <JobHeader job={job} />
        {(error || failureCount > 0) && (
          <p className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
            <WifiOff className="size-4 shrink-0" aria-hidden />
            Lost contact with the server. Showing the last known progress; retrying…
          </p>
        )}
        <section className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
          <PipelineTracker stages={job.stages} />
        </section>
        <ErrorPanel job={job} />
        <DeckCard job={job} />
      </div>

      {job.deck && job.deck.length > 0 && (
        <DeckPreview slides={job.deck} datasetName={job.filename} />
      )}

      {job.insights ? (
        <>
          <AnswersSection
            answers={job.insights.questions_answered}
            userQuestion={job.options.question}
            titles={titles}
          />
          <section className="space-y-4" aria-labelledby="insights-heading">
            <h2 id="insights-heading" className="text-lg font-semibold tracking-tight">
              Insights
            </h2>
            <ExecutiveSummary insights={job.insights} grounding={job.grounding} titles={titles} />
            <div className="grid gap-4 lg:grid-cols-2">
              <NotesList title="Recommended actions" items={job.insights.recommended_actions} />
              <HypothesesList hypotheses={job.insights.hypotheses} titles={titles} />
              <QuestionsList questions={job.insights.open_questions} />
              <NotesList title="Data quality notes" items={job.insights.data_quality_notes} />
            </div>
          </section>
        </>
      ) : (
        analyzing && <InsightsSkeleton />
      )}

      {job.findings && <FindingsSection findings={job.findings} />}

      {job.profile && (
        <section className="space-y-4" aria-labelledby="dataset-heading">
          <h2 id="dataset-heading" className="text-lg font-semibold tracking-tight">
            Dataset profile
          </h2>
          <SummaryCards profile={job.profile} />
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <MissingValues columns={job.profile.columns} />
            <CorrelationHeatmap correlation={job.profile.correlation} />
          </div>
          <ColumnTable columns={job.profile.columns} />
        </section>
      )}
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <section aria-busy="true" aria-label="Generating insights" className="space-y-4">
      <div className="h-6 w-28 animate-pulse rounded bg-surface-muted" />
      <div className="h-28 animate-pulse rounded-2xl bg-surface-muted" />
      <div className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-muted" />
        ))}
      </div>
    </section>
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
  const target = job.options.target_column ?? job.roles?.targets[0];
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="grid size-10 place-items-center rounded-lg bg-accent-soft text-accent">
        <FileSpreadsheet className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-xl font-semibold tracking-tight">{job.filename}</h1>
        <p className="text-sm text-muted">
          {job.options.num_slides} slides · {job.options.tone} tone · for {job.options.audience}
          {target && (
            <>
              {" "}
              · outcome: <span className="font-medium text-foreground">{target}</span>
            </>
          )}
        </p>
        {job.options.question && (
          <p className="mt-1 text-sm">
            <span className="text-muted">Question: </span>
            {job.options.question}
          </p>
        )}
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
