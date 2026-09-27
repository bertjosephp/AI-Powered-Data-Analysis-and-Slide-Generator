"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { getHealth } from "@/lib/api/client";
import type { Health } from "@/lib/api/types";

/**
 * Tracks whether the API is awake. The hosted demo's free server sleeps when
 * idle and takes up to a minute to wake, so instead of failing silently the app
 * shows a "waking up" state and keeps retrying until the server answers.
 */
export type ServerState = "checking" | "waking" | "ready";

type ServerStatus = {
  state: ServerState;
  /** Seconds spent waiting for the server to wake (0 unless waking). */
  waitedSeconds: number;
  health: Health | null;
  refresh: () => void;
};

// Without a provider (e.g. in component tests) the server is assumed awake.
const Context = createContext<ServerStatus>({
  state: "ready",
  waitedSeconds: 0,
  health: null,
  refresh: () => {},
});

export const WAKE_THRESHOLD_MS = 1500;
export const RETRY_INTERVAL_MS = 3000;
const ATTEMPT_TIMEOUT_MS = 10_000;

export function ServerStatusProvider({
  children,
  wakeThresholdMs = WAKE_THRESHOLD_MS,
  retryIntervalMs = RETRY_INTERVAL_MS,
}: {
  children: React.ReactNode;
  wakeThresholdMs?: number;
  retryIntervalMs?: number;
}) {
  const [state, setState] = useState<ServerState>("checking");
  const [health, setHealth] = useState<Health | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const cancelled = useRef(false);

  const check = useCallback(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
    try {
      const result = await getHealth(controller.signal);
      if (!cancelled.current) {
        setHealth(result);
        setState("ready");
      }
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
    }
  }, []);

  useEffect(() => {
    cancelled.current = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    // Only call it "waking" if the first answer is slow; a quick answer never flashes the banner.
    const slow = setTimeout(() => {
      if (!cancelled.current) {
        setState((s) => (s === "ready" ? s : "waking"));
        setStartedAt((t) => t ?? Date.now());
      }
    }, wakeThresholdMs);

    const loop = async () => {
      const ok = await check();
      if (ok || cancelled.current) {
        clearTimeout(slow);
        return;
      }
      setState("waking");
      setStartedAt((t) => t ?? Date.now());
      retry = setTimeout(loop, retryIntervalMs);
    };
    void loop();
    return () => {
      cancelled.current = true;
      clearTimeout(slow);
      clearTimeout(retry);
    };
  }, [check, wakeThresholdMs, retryIntervalMs]);

  useEffect(() => {
    if (state !== "waking") return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [state]);

  const refresh = useCallback(() => void check(), [check]);
  const waitedSeconds =
    state === "waking" && startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : 0;

  return (
    <Context.Provider value={{ state, waitedSeconds, health, refresh }}>
      {children}
    </Context.Provider>
  );
}

export function useServerStatus(): ServerStatus {
  return useContext(Context);
}
