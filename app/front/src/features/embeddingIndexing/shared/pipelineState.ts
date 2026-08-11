import type {
  EmbeddingIndexingStage,
  EmbeddingIndexingState,
} from "../../dashboard/dashboardTypes.js";

export type MissingPipelineResource =
  | "embeddingRun"
  | "embeddingBundle"
  | "indexingRun"
  | "retrievalProfile";

export type CorpusBatchProgress = {
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  currentLabel: string | null;
};

function fallbackStageForMissingResource(
  resource: MissingPipelineResource,
  activeStage: EmbeddingIndexingStage,
): EmbeddingIndexingStage {
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

export function clearMissingPipelineResource(
  state: EmbeddingIndexingState,
  resource: MissingPipelineResource,
): Partial<EmbeddingIndexingState> {
  const patch: Partial<EmbeddingIndexingState> = {
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

