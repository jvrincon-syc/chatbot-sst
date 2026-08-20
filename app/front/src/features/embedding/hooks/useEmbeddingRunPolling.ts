import { loadEmbeddingRun } from "../embeddingApi.js";
import { embeddingRunIsTerminal } from "../embeddingState.js";
import { usePollingLoop } from "../../embeddingIndexing/shared/usePollingLoop.js";
import type { PipelineUiError } from "../../../shared/api/apiTypes.js";
import type { EmbeddingRun } from "../embeddingTypes.js";

export type EmbeddingRunPollingState = {
  run: EmbeddingRun | null;
  polling: boolean;
  error: PipelineUiError | null;
  timedOut: boolean;
};

// Polls a non-terminal embedding run until it reaches a terminal state, using
// the shared abortable, visibility-aware polling loop.
export function useEmbeddingRunPolling(
  embeddingRunId: string | null,
  options?: { intervalMs?: number; enabled?: boolean },
): EmbeddingRunPollingState {
  const { value, polling, error, timedOut } = usePollingLoop<EmbeddingRun>({
    resourceId: embeddingRunId,
    enabled: options?.enabled,
    intervalMs: options?.intervalMs,
    fetchOnce: (signal) => loadEmbeddingRun(embeddingRunId as string, { signal }),
    isTerminal: (run) => embeddingRunIsTerminal(run.status),
  });

  return { run: value, polling, error, timedOut };
}
