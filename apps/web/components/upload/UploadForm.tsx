"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createJob } from "@/lib/api/client";
import { type AnalysisOptions, DEFAULT_OPTIONS } from "@/lib/api/types";

import { FileDropzone } from "./FileDropzone";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20";

export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<AnalysisOptions>(DEFAULT_OPTIONS);
  const [clientError, setClientError] = useState<string | null>(null);

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
        onFileChange={(f) => {
          setFile(f);
          setClientError(null);
          mutation.reset();
        }}
        onReject={(message) => {
          setFile(null);
          setClientError(message);
        }}
      />

      <fieldset className="mt-6 grid gap-4 sm:grid-cols-2" disabled={busy}>
        <legend className="mb-3 text-sm font-medium">Deck options</legend>
        <label className="text-sm text-muted">
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
        <label className="text-sm text-muted">
          Download format
          <select
            className={fieldClass}
            value={options.export_as ?? "none"}
            onChange={(e) =>
              update(
                "export_as",
                e.target.value === "none" ? null : (e.target.value as "pdf" | "pptx"),
              )
            }
          >
            <option value="pdf">PDF</option>
            <option value="pptx">PowerPoint (.pptx)</option>
            <option value="none">None (view in Gamma only)</option>
          </select>
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
