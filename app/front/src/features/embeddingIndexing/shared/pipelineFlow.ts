export type PipelineStage = "embedding" | "indexing" | "activation" | "retrieval";

export type PipelineRunKind = "embedding" | "indexing";

const RUN_TERMINAL_STATUSES: readonly string[] = [
  "completed",
  "failed",
  "cancelled",
  "blocked",
];

// The pipeline follows Embedding -> Indexing -> Activation -> Retrieval, with
// Activation as its own stage between Indexing and Retrieval.
export function pipelineStageOrder(): readonly PipelineStage[] {
  return ["embedding", "indexing", "activation", "retrieval"] as const;
}

// Polling continues only while a run is non-terminal. Both embedding and
// indexing runs share the same terminal set per the backend contract.
export function shouldContinuePolling(kind: PipelineRunKind, status: string): boolean {
  void kind;
  return !RUN_TERMINAL_STATUSES.includes(status);
}

export function shouldAdvanceToIndexing(options: {
  activeStage: PipelineStage;
  producedBundleId: string | null;
  indexingRunId: string | null;
}): boolean {
  return (
    options.activeStage === "embedding" &&
    options.producedBundleId !== null &&
    options.indexingRunId === null
  );
}
