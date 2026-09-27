"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Database, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createJob, fetchSampleFile, listSamples } from "@/lib/api/client";
import { type AnalysisOptions, DEFAULT_OPTIONS, type Sample } from "@/lib/api/types";
import { readCsvHeader } from "@/lib/csvHeader";
import { cn } from "@/lib/utils";

import { FileDropzone } from "./FileDropzone";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<AnalysisOptions>(DEFAULT_OPTIONS);
  const [clientError, setClientError] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[] | null>(null);
  const [activeSample, setActiveSample] = useState<string | null>(null);
  const samples = useQuery({ queryKey: ["samples"], queryFn: listSamples, staleTime: Infinity });

  const mutation = useMutation({
    mutationFn: ({ file, options }: { file: File; options: AnalysisOptions }) =>
      createJob(file, options),
    onSuccess: ({ job_id }) => router.push(`/jobs/${job_id}`),
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
      className="rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (file) mutation.mutate({ file, options });
      }}
    >
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

      {samples.data && samples.data.length > 0 && (
        <div className="mt-4">
          <p className="text-sm text-muted">Or try an example dataset:</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {samples.data.map((sample) => (
              <button
                key={sample.name}
                type="button"
                disabled={busy || loadSample.isPending}
                onClick={() => loadSample.mutate(sample)}
                title={`${sample.description} (${sample.rows.toLocaleString("en-US")} rows × ${sample.columns} columns)`}
                aria-pressed={activeSample === sample.name}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition disabled:opacity-50",
                  activeSample === sample.name
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-border hover:border-accent/50 hover:bg-accent-soft/50",
                )}
              >
                <Database className="size-3.5" aria-hidden />
                {sample.title}
              </button>
            ))}
          </div>
        </div>
      )}

      <fieldset className="mt-6 grid gap-4" disabled={busy}>
        <legend className="mb-3 text-sm font-medium">What should the analysis focus on?</legend>
        <label className="text-sm text-muted">
          What do you want to learn? <span className="text-xs">(optional)</span>
          <textarea
            className={cn(fieldClass, "min-h-20 resize-y")}
            value={options.question ?? ""}
            maxLength={300}
            placeholder="e.g. Why are customers churning, and what are the warning signs?"
            onChange={(e) => update("question", e.target.value || null)}
          />
        </label>
        <label className="text-sm text-muted">
          Outcome to explain <span className="text-xs">(optional)</span>
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

      <fieldset className="mt-6 grid gap-4 sm:grid-cols-2" disabled={busy}>
        <legend className="mb-3 text-sm font-medium">Deck options</legend>
        <label className="text-sm text-muted sm:col-span-2">
          Audience
          <input
            className={fieldClass}
            value={options.audience}
            maxLength={200}
            onChange={(e) => update("audience", e.target.value)}
          />
        </label>
        <label className="text-sm text-muted">
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
        <label className="text-sm text-muted">
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

      {error && (
        <p
          role="alert"
          className="mt-5 flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={!file || busy || options.audience.trim() === ""}
        className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 font-medium text-accent-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden /> Uploading…
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
