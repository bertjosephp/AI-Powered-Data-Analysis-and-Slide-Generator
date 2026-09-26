"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, getJob } from "@/lib/api/client";
import type { JobState } from "@/lib/api/types";

export const POLL_INTERVAL_MS = 2000;

export function isTerminal(job: JobState | undefined) {
  return job?.status === "completed" || job?.status === "failed";
}

export function jobQueryKey(jobId: string) {
  return ["job", jobId] as const;
}

/** Polls GET /jobs/{id} until the job completes or fails. */
export function useJobPolling(jobId: string, intervalMs = POLL_INTERVAL_MS) {
  return useQuery({
    queryKey: jobQueryKey(jobId),
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => (isTerminal(query.state.data) ? false : intervalMs),
    refetchIntervalInBackground: true,
    // A missing job won't reappear; network blips are worth a couple of retries.
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 3,
  });
}
