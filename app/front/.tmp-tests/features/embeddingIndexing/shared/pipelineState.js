function fallbackStageForMissingResource(resource, activeStage) {
    if (resource === "embeddingBundle") {
        return "embedding";
    }
    if (resource === "indexingRun" && (activeStage === "activation" || activeStage === "retrieval")) {
        return "indexing";
    }
    if (resource === "retrievalProfile" && activeStage === "retrieval") {
        return "activation";
    }
    return activeStage;
}
export function clearMissingPipelineResource(state, resource) {
    const patch = {
        activeStage: fallbackStageForMissingResource(resource, state.activeStage),
    };
    if (resource === "embeddingRun") {
        patch.activeEmbeddingRunId = null;
        return patch;
    }
    if (resource === "embeddingBundle") {
        patch.selectedEmbeddingBundleId = null;
        patch.activeIndexingRunId = null;
        patch.activeActivationRunId = null;
        patch.selectedRetrievalProfileId = null;
        return patch;
    }
    if (resource === "indexingRun") {
        patch.activeIndexingRunId = null;
        patch.activeActivationRunId =
            state.activeActivationRunId === state.activeIndexingRunId
                ? null
                : state.activeActivationRunId;
        return patch;
    }
    patch.selectedRetrievalProfileId = null;
    return patch;
}
