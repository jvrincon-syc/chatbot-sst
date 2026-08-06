import { useEffect, useRef, useState } from "react";
import { mapPipelineError } from "./errorMapping.js";
import type { PipelineUiError } from "./apiTypes.js";

const DEFAULT_POLL_INTERVAL_MS = 1000;
const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;

export type PollingLoopState<T> = {
  value: T | null;
  polling: boolean;
  error: PipelineUiError | null;
  timedOut: boolean;
};

export type PollingLoopOptions<T> = {
  // Resource identity. When it changes, the loop resets and restarts.
  resourceId: string | null;
  enabled?: boolean;
  intervalMs?: number;
  timeoutMs?: number;
  // Fetches one snapshot. Must honor the abort signal.
  fetchOnce: (signal: AbortSignal) => Promise<T>;
  // Whether the fetched value is terminal and polling should stop.
  isTerminal: (value: T) => boolean;
};

// Generic polling loop: abortable via AbortController, non-overlapping (each
// request is awaited before the next is scheduled), visibility-aware (pauses
// while the tab is hidden and refreshes on return), terminal-state aware, and
// bounded by an overall UI timeout.
export function usePollingLoop<T>(options: PollingLoopOptions<T>): PollingLoopState<T> {
  const {
    resourceId,
    enabled = true,
    intervalMs = DEFAULT_POLL_INTERVAL_MS,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fetchOnce,
    isTerminal,
  } = options;

  const [value, setValue] = useState<T | null>(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<PipelineUiError | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  const valueRef = useRef<T | null>(null);
  const fetchOnceRef = useRef(fetchOnce);
  const isTerminalRef = useRef(isTerminal);
  fetchOnceRef.current = fetchOnce;
  isTerminalRef.current = isTerminal;

  useEffect(() => {
    valueRef.current = null;
    setValue(null);
    setError(null);
    setTimedOut(false);

    if (!resourceId || !enabled) {
      setPolling(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const controller = new AbortController();
    const deadline = Date.now() + timeoutMs;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const isDone = () => {
      const current = valueRef.current;
      return current !== null && isTerminalRef.current(current);
    };

    const scheduleNext = () => {
      if (cancelled || isDone()) {
        setPolling(false);
        return;
      }
      if (Date.now() >= deadline) {
        setTimedOut(true);
        setPolling(false);
        return;
      }
      if (document.hidden) {
        setPolling(false);
        return;
      }
      clearTimer();
      timer = setTimeout(() => void tick(), intervalMs);
    };

    const tick = async () => {
      if (cancelled || document.hidden) return;
      setPolling(true);
      try {
        const next = await fetchOnceRef.current(controller.signal);
        if (cancelled) return;
        valueRef.current = next;
        setValue(next);
        setError(null);
        if (isTerminalRef.current(next)) {
          setPolling(false);
          return;
        }
        scheduleNext();
      } catch (caught) {
        if (cancelled || controller.signal.aborted) return;
        setError(mapPipelineError(caught));
        setPolling(false);
        scheduleNext();
      }
    };

    const handleVisibility = () => {
      if (cancelled) return;
      if (!document.hidden && !isDone()) {
        void tick();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    void tick();

    return () => {
      cancelled = true;
      clearTimer();
      controller.abort();
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [resourceId, enabled, intervalMs, timeoutMs]);

  return { value, polling, error, timedOut };
}
