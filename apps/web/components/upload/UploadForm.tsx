"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Database,
  HeartPulse,
  Loader2,
  Repeat,
  ShoppingCart,
  Sparkles,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createJob, fetchSampleFile, listSamples } from "@/lib/api/client";
import { type AnalysisOptions, DEFAULT_OPTIONS, type Sample } from "@/lib/api/types";
import { readCsvHeader } from "@/lib/csvHeader";
import { useServerStatus } from "@/lib/hooks/useServerStatus";
import { cn } from "@/lib/utils";

import { FileDropzone } from "./FileDropzone";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm font-normal shadow-xs transition placeholder:text-muted/70 focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/15";

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<AnalysisOptions>(DEFAULT_OPTIONS);
  const [clientError, setClientError] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[] | null>(null);
  const [activeSample, setActiveSample] = useState<string | null>(null);
  const server = useServerStatus();
  const serverReady = server.state === "ready";
  const samples = useQuery({
    queryKey: ["samples"],
    queryFn: listSamples,
    staleTime: Infinity,
    enabled: serverReady,
  });

  const mutation = useMutation({
    mutationFn: ({ file, options }: { file: File; options: AnalysisOptions }) =>
      createJob(file, options),
    onSuccess: ({ job_id }) => {
      server.refresh(); // this run used one of the visitor's demo analyses
      router.push(`/jobs/${job_id}`);
    },
  });

  // Once the job is created we're navigating away; keep the form locked meanwhile.
  const busy = mutation.isPending || mutation.isSuccess;
  const error =
    clientError ??
    (mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error
        ? "Something went wrong. Please try again."
        : null);

  const update = <K extends keyof AnalysisOptions>(key: K, value: AnalysisOptions[K]) =>
    setOptions((prev) => ({ ...prev, [key]: value }));

  async function chooseFile(f: File | null, fromSample: string | null = null) {
    setFile(f);
    setActiveSample(fromSample);
    setClientError(null);
    mutation.reset();
    const header = f ? await readCsvHeader(f).catch(() => null) : null;
    setColumns(header);
    // Drop a previously chosen outcome that this file doesn't have.
    setOptions((prev) =>
      prev.target_column && header && !header.includes(prev.target_column)
        ? { ...prev, target_column: null }
        : prev,
    );
  }

  const loadSample = useMutation({
    mutationFn: fetchSampleFile,
    onSuccess: async (sampleFile, sample: Sample) => {
      await chooseFile(sampleFile, sample.name);
      setOptions((prev) => ({
        ...prev,
        question: sample.suggested_question,
        target_column: sample.suggested_target,
      }));
    },
    onError: (e) => setClientError(e instanceof ApiError ? e.message : "Could not load the sample."),
  });

  return (
    <form
      className="rounded-3xl border border-border bg-surface p-5 shadow-card sm:p-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (file) mutation.mutate({ file, options });
      }}
    >
      <Step n={1} title="Choose your data">
        <FileDropzone
          file={file}
          disabled={busy}
          onFileChange={(f) => void chooseFile(f)}
          onReject={(message) => {
            setFile(null);
            setColumns(null);
            setClientError(message);
          }}
        />
        {!samples.data && (samples.isPending || !serverReady) && (
          <div className="mt-4" aria-hidden data-testid="sample-skeletons">
            <div className="h-3 w-40 animate-pulse rounded bg-surface-muted" />
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-[3.75rem] animate-pulse rounded-xl bg-surface-muted" />
              ))}
            </div>
          </div>
        )}
        {samples.data && samples.data.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium tracking-wide text-muted uppercase">
              Or start from an example
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {samples.data.map((sample) => {
                const Icon = SAMPLE_ICONS[sample.name] ?? Database;
                const active = activeSample === sample.name;
                return (
                  <button
                    key={sample.name}
                    type="button"
                    disabled={busy || loadSample.isPending}
                    onClick={() => loadSample.mutate(sample)}
                    title={sample.description}
                    aria-pressed={active}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border p-3 text-left transition disabled:opacity-50",
                      active
                        ? "border-accent bg-accent-soft"
                        : "border-border hover:border-accent/40 hover:bg-surface-muted",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-9 shrink-0 place-items-center rounded-lg",
                        active ? "bg-accent text-accent-foreground" : "bg-surface-muted text-accent",
                      )}
                    >
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{sample.title}</span>
                      <span className="block text-xs text-muted">
                        {sample.rows.toLocaleString("en-US")} rows × {sample.columns} columns
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </Step>

      <Step n={2} title="Focus the analysis" hint="Optional">
        <fieldset className="grid gap-4" disabled={busy}>
          <legend className="sr-only">What should the analysis focus on?</legend>
          <label className="text-sm font-medium">
            What do you want to learn?
            <textarea
              className={cn(fieldClass, "min-h-20 resize-y")}
              value={options.question ?? ""}
              maxLength={300}
              placeholder="e.g. Why are customers churning, and what are the warning signs?"
              onChange={(e) => update("question", e.target.value || null)}
            />
          </label>
          <label className="text-sm font-medium">
            Outcome to explain
            {columns ? (
              <select
                className={fieldClass}
                value={options.target_column ?? ""}
                onChange={(e) => update("target_column", e.target.value || null)}
              >
                <option value="">Detect automatically</option>
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={fieldClass}
                value={options.target_column ?? ""}
                maxLength={200}
                placeholder="Column name, e.g. churned or revenue. Leave blank to detect."
                onChange={(e) => update("target_column", e.target.value.trim() || null)}
              />
            )}
          </label>
        </fieldset>
      </Step>

      <Step n={3} title="Deck options" last>
        <fieldset className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem_6rem]" disabled={busy}>
          <legend className="sr-only">Deck options</legend>
          <label className="text-sm font-medium">
            Audience
            <input
              className={fieldClass}
              value={options.audience}
              maxLength={200}
              onChange={(e) => update("audience", e.target.value)}
            />
          </label>
          <label className="text-sm font-medium">
            Tone
            <select
              className={fieldClass}
              value={options.tone}
              onChange={(e) => update("tone", e.target.value as AnalysisOptions["tone"])}
            >
              <option value="executive">Executive</option>
              <option value="technical">Technical</option>
              <option value="casual">Casual</option>
            </select>
          </label>
          <label className="text-sm font-medium">
            Slides
            <input
              type="number"
              className={fieldClass}
              min={4}
              max={25}
              value={options.num_slides}
              onChange={(e) =>
                update("num_slides", Math.min(25, Math.max(4, Number(e.target.value) || 4)))
              }
            />
          </label>
        </fieldset>
      </Step>

      {error && (
        <p
          role="alert"
          className="mt-5 flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}

      <DemoHint />

      <button
        type="submit"
        disabled={!file || busy || !serverReady || options.audience.trim() === ""}
        className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-3 font-medium text-white shadow-sm transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden /> Uploading…
          </>
        ) : !serverReady ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden /> Waiting for server…
          </>
        ) : (
          <>
            Analyze and build deck <ArrowRight className="size-4" aria-hidden />
          </>
        )}
      </button>
    </form>
  );
}

/** Tells visitors of the hosted demo how many Claude-powered runs they have left. */
function DemoHint() {
  const demo = useServerStatus().health?.demo;
  if (!demo) return null;
  const live = demo.claude_available && demo.runs_left_this_hour > 0;
  const left = demo.runs_left_this_hour;
  return (
    <p className="mt-5 flex items-center gap-2 text-xs text-muted" data-testid="demo-hint">
      <Sparkles className={cn("size-3.5 shrink-0", live && "text-accent")} aria-hidden />
      {live
        ? `Live demo · ${left} Claude ${left === 1 ? "analysis" : "analyses"} left this hour`
        : "Live demo · Claude limit reached, so runs use the offline analyst for now"}
    </p>
  );
}

const SAMPLE_ICONS: Record<string, typeof Database> = {
  ecommerce_orders: ShoppingCart,
  saas_churn: Repeat,
  hr_attrition: Users,
  hospital_readmissions: HeartPulse,
};

function Step({
  n,
  title,
  hint,
  last,
  children,
}: {
  n: number;
  title: string;
  hint?: string;
  last?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("pb-6", !last && "mb-6 border-b border-border")}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <span className="grid size-5 place-items-center rounded-full bg-accent-soft text-[11px] text-accent">
          {n}
        </span>
        {title}
        {hint && <span className="font-normal text-muted">· {hint}</span>}
      </h2>
      {children}
    </section>
  );
}
