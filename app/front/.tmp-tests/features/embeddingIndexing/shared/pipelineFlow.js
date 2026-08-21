const RUN_TERMINAL_STATUSES = [
    "completed",
    "failed",
    "cancelled",
    "blocked",
];
// The pipeline follows Embedding -> Indexing -> Activation -> Retrieval, with
// Activation as its own stage between Indexing and Retrieval.
export function pipelineStageOrder() {
    return ["embedding", "indexing", "activation", "retrieval"];
}
// Polling continues only while a run is non-terminal. Both embedding and
// indexing runs share the same terminal set per the backend contract.
export function shouldContinuePolling(kind, status) {
    void kind;
    return !RUN_TERMINAL_STATUSES.includes(status);
}
export function shouldAdvanceToIndexing(options) {
    return (options.activeStage === "embedding" &&
        options.producedBundleId !== null &&
        options.indexingRunId === null &&
        !options.embeddingCorpusBusy);
}
