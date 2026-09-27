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
import { SectionHeader } from "@/components/ui/SectionHeader";
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
      <div className="mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 text-center shadow-card">
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
  const cited = new Set(
    [
      ...(job.insights?.questions_answered ?? []),
      ...(job.insights?.key_findings ?? []),
      ...(job.insights?.hypotheses ?? []),
    ].flatMap((item) => item.finding_ids),
  );
  const current = job.stages.find((s) => s.status === "running");
  const sections = [
    job.insights && { id: "answers", label: job.options.question ? "Your answer" : "Answers" },
    job.deck?.length && { id: "slides", label: "Slides" },
    job.findings && { id: "findings", label: "Findings" },
    job.insights && { id: "insights", label: "Insights" },
    job.profile && { id: "dataset", label: "Dataset" },
  ].filter(Boolean) as { id: string; label: string }[];

  return (
    <div className="grid gap-8 lg:grid-cols-[17rem_minmax(0,1fr)] xl:gap-12">
      <p className="sr-only" aria-live="polite">
        {job.status === "completed"
          ? "Analysis complete. Your deck is ready."
          : job.status === "failed"
            ? "The analysis failed."
            : current
              ? `${current.label}…`
              : "Queued."}
      </p>

      <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
        <JobSummary job={job} />
        <section className="rounded-2xl border border-border bg-surface p-4 shadow-card">
          <h2 className="mb-4 text-xs font-semibold tracking-wider text-muted uppercase">Progress</h2>
          <PipelineTracker stages={job.stages} />
        </section>
        <DeckCard job={job} />
        {sections.length > 0 && (
          <nav aria-label="On this page" className="hidden px-1 lg:block">
            <p className="mb-2 text-xs font-semibold tracking-wider text-muted uppercase">
              On this page
            </p>
            <ul className="space-y-1 text-sm">
              {sections.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className="block rounded-md px-2 py-1 text-muted transition hover:bg-surface-muted hover:text-foreground"
                  >
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </aside>

      <div className="min-w-0 space-y-14">
        {(error || failureCount > 0) && (
          <p className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
            <WifiOff className="size-4 shrink-0" aria-hidden />
            Lost contact with the server. Showing the last known progress; retrying…
          </p>
        )}
        <ErrorPanel job={job} />

        {job.insights ? (
          <div id="answers" className="scroll-mt-24">
            <AnswersSection
              answers={job.insights.questions_answered}
              userQuestion={job.options.question}
              titles={titles}
            />
          </div>
        ) : (
          analyzing && <InsightsSkeleton />
        )}

        {job.deck && job.deck.length > 0 && (
          <div id="slides" className="scroll-mt-24">
            <DeckPreview slides={job.deck} datasetName={job.filename} />
          </div>
        )}

        {job.findings && (
          <div id="findings" className="scroll-mt-24">
            <FindingsSection findings={job.findings} cited={cited} />
          </div>
        )}

        {job.insights && (
          <section id="insights" className="scroll-mt-24" aria-labelledby="insights-heading">
            <SectionHeader
              id="insights-heading"
              eyebrow="Narrative"
              title="Insights"
              description="The summary, recommended actions, hypotheses to test and open questions."
            />
            <div className="space-y-4">
              <ExecutiveSummary insights={job.insights} grounding={job.grounding} titles={titles} />
              <div className="grid gap-4 xl:grid-cols-2">
                <NotesList title="Recommended actions" items={job.insights.recommended_actions} />
                <HypothesesList hypotheses={job.insights.hypotheses} titles={titles} />
                <QuestionsList questions={job.insights.open_questions} />
                <NotesList title="Data quality notes" items={job.insights.data_quality_notes} />
              </div>
            </div>
          </section>
        )}

        {job.profile && (
          <section id="dataset" className="scroll-mt-24" aria-labelledby="dataset-heading">
            <SectionHeader
              id="dataset-heading"
              eyebrow="Data"
              title="Dataset profile"
              description="What was analyzed: size, completeness, correlations and every column."
            />
            <div className="space-y-4">
              <SummaryCards profile={job.profile} />
              <div className="grid items-start gap-4 xl:grid-cols-2">
                <MissingValues columns={job.profile.columns} />
                <CorrelationHeatmap correlation={job.profile.correlation} />
              </div>
              <details className="group rounded-2xl border border-border bg-surface shadow-card">
                <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-sm font-medium">
                  All {job.profile.columns.length} columns
                  <span className="text-muted transition group-open:rotate-180" aria-hidden>
                    ▾
                  </span>
                </summary>
                <div className="border-t border-border [&>section]:rounded-none [&>section]:border-0 [&>section]:shadow-none">
                  <ColumnTable columns={job.profile.columns} />
                </div>
              </details>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <section aria-busy="true" aria-label="Generating insights" className="space-y-4">
      <div className="h-6 w-40 animate-pulse rounded bg-surface-muted" />
      <div className="h-32 animate-pulse rounded-2xl bg-surface-muted" />
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

function JobSummary({ job }: { job: JobState }) {
  const badge = STATUS_BADGE[job.status];
  const target = job.options.target_column ?? job.roles?.targets[0];
  return (
    <section className="rounded-2xl border border-border bg-surface p-4 shadow-card">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
          <FileSpreadsheet className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-semibold tracking-tight" title={job.filename}>
            {job.filename}
          </h1>
          <span className={cn("mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium", badge.className)}>
            {badge.label}
          </span>
        </div>
      </div>
      <dl className="mt-4 space-y-2 border-t border-border pt-3 text-sm">
        {target && (
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Outcome</dt>
            <dd className="truncate font-medium">{target}</dd>
          </div>
        )}
        <div className="flex justify-between gap-3">
          <dt className="text-muted">Deck</dt>
          <dd>
            {job.options.num_slides} slides · {job.options.tone}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted">Audience</dt>
          <dd className="truncate">{job.options.audience}</dd>
        </div>
      </dl>
      {job.options.question && (
        <p className="mt-3 rounded-lg bg-surface-muted p-2.5 text-sm">
          <span className="block text-xs text-muted">Question</span>
          {job.options.question}
        </p>
      )}
    </section>
  );
}

function JobSkeleton() {
  return (
    <div
      className="grid animate-pulse gap-8 lg:grid-cols-[17rem_minmax(0,1fr)]"
      aria-busy="true"
      aria-label="Loading analysis"
    >
      <div className="space-y-4">
        <div className="h-40 rounded-2xl bg-surface-muted" />
        <div className="h-64 rounded-2xl bg-surface-muted" />
      </div>
      <div className="space-y-4">
        <div className="h-8 w-64 rounded bg-surface-muted" />
        <div className="h-40 rounded-2xl bg-surface-muted" />
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="h-32 rounded-xl bg-surface-muted" />
          ))}
        </div>
      </div>
    </div>
  );
}
