import type { z } from "zod";

import {
  type AnalysisOptions,
  ErrorEnvelopeSchema,
  type JobCreated,
  JobCreatedSchema,
  type JobState,
  JobStateSchema,
  type Health,
  HealthSchema,
  type Sample,
  SampleSchema,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the analysis server. Is it running?");
  }

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const envelope = ErrorEnvelopeSchema.safeParse(body);
    if (envelope.success) {
      throw new ApiError(res.status, envelope.data.error.code, envelope.data.error.message);
    }
    throw new ApiError(res.status, `HTTP_${res.status}`, `Request failed (${res.status}).`);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    console.error("Unexpected API response", path, parsed.error);
    throw new ApiError(res.status, "BAD_RESPONSE", "The server sent an unexpected response.");
  }
  return parsed.data;
}

export function createJob(file: File, options: AnalysisOptions): Promise<JobCreated> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("options", JSON.stringify(options));
  return request("/jobs", JobCreatedSchema, { method: "POST", body: form });
}

export function getJob(jobId: string): Promise<JobState> {
  return request(`/jobs/${encodeURIComponent(jobId)}`, JobStateSchema, { cache: "no-store" });
}

export function retryJob(jobId: string): Promise<JobCreated> {
  return request(`/jobs/${encodeURIComponent(jobId)}/retry`, JobCreatedSchema, {
    method: "POST",
  });
}

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return request("/health", HealthSchema, { cache: "no-store", signal });
}

export function listSamples(): Promise<Sample[]> {
  return request("/samples", SampleSchema.array());
}

/** Fetches a bundled sample dataset as a File, ready to upload like a user's own. */
export async function fetchSampleFile(sample: Sample): Promise<File> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/samples/${encodeURIComponent(sample.name)}.csv`);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the analysis server. Is it running?");
  }
  if (!res.ok) throw new ApiError(res.status, `HTTP_${res.status}`, "Could not load the sample dataset.");
  return new File([await res.text()], sample.filename, { type: "text/csv" });
}
