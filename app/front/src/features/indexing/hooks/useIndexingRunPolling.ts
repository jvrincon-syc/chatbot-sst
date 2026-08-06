import { loadIndexingRun } from "../indexingApi.js";
import { indexingRunIsTerminal } from "../indexingState.js";
import { usePollingLoop } from "../../embeddingIndexing/shared/usePollingLoop.js";
import type { PipelineUiError } from "../../embeddingIndexing/shared/apiTypes.js";
import type { IndexingRun } from "../indexingTypes.js";

export type IndexingRunPollingState = {
  run: IndexingRun | null;
  polling: boolean;
  error: PipelineUiError | null;
  timedOut: boolean;
};

// Polls a non-terminal indexing run until it reaches a terminal state, using the
// shared abortable, visibility-aware polling loop.
export function useIndexingRunPolling(
  runId: string | null,
  options?: { intervalMs?: number; enabled?: boolean },
): IndexingRunPollingState {
  const { value, polling, error, timedOut } = usePollingLoop<IndexingRun>({
    resourceId: runId,
    enabled: options?.enabled,
    intervalMs: options?.intervalMs,
    fetchOnce: (signal) => loadIndexingRun(runId as string, { signal }),
    isTerminal: (run) => indexingRunIsTerminal(run.status),
  });

  return { run: value, polling, error, timedOut };
}
