import type { PipelineStage } from "./shared/pipelineFlow.js";
import type { PipelineStageStatus } from "./PipelineStepper.js";
import type { EmbeddingIndexingStage } from "../dashboard/dashboardTypes.js";

const FAILED_STATUSES: readonly string[] = ["failed", "cancelled", "blocked"];

export type StageStatusInput = {
  embeddingRunStatus: string | null;
  embeddingBundleReady: boolean;
  indexingRunStatus: string | null;
  activationStatus: string | null;
  retrievalProfileId: string | null;
  retrievalReady: boolean;
  activeStage: EmbeddingIndexingStage;
};

// Derives a text status for each of the four stages from the current pipeline
// snapshot. Used by the stepper so progress is conveyed with words, not color.
export function deriveStageStatus(
  input: StageStatusInput,
): Record<PipelineStage, PipelineStageStatus> {
  return {
    embedding: embeddingStatus(input),
    indexing: indexingStatus(input),
    activation: activationStatus(input),
    retrieval: retrievalStatus(input),
  };
}

function withActive(
  stage: PipelineStage,
  activeStage: EmbeddingIndexingStage,
  status: PipelineStageStatus,
): PipelineStageStatus {
  if (status === "pending" && stage === activeStage) {
    return "active";
  }
  return status;
}

function embeddingStatus(input: StageStatusInput): PipelineStageStatus {
  const { embeddingRunStatus, embeddingBundleReady } = input;
  if (embeddingBundleReady || embeddingRunStatus === "completed") return "done";
  if (embeddingRunStatus && FAILED_STATUSES.includes(embeddingRunStatus)) return "blocked";
  if (embeddingRunStatus === "pending" || embeddingRunStatus === "running") return "active";
  return withActive("embedding", input.activeStage, "pending");
}

function indexingStatus(input: StageStatusInput): PipelineStageStatus {
  const { indexingRunStatus } = input;
  if (indexingRunStatus === "completed") return "done";
  if (indexingRunStatus && FAILED_STATUSES.includes(indexingRunStatus)) return "blocked";
  if (indexingRunStatus === "pending" || indexingRunStatus === "running") return "active";
  return withActive("indexing", input.activeStage, "pending");
}

function activationStatus(input: StageStatusInput): PipelineStageStatus {
  const { activationStatus: status, retrievalProfileId } = input;
  if (retrievalProfileId || status === "active") return "done";
  if (status && FAILED_STATUSES.includes(status)) return "blocked";
  return withActive("activation", input.activeStage, "pending");
}

function retrievalStatus(input: StageStatusInput): PipelineStageStatus {
  const { retrievalProfileId, retrievalReady } = input;
  if (retrievalReady) return "done";
  if (!retrievalProfileId) return withActive("retrieval", input.activeStage, "pending");
  return withActive("retrieval", input.activeStage, "pending");
}
