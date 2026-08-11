import assert from "node:assert/strict";

import { clearMissingPipelineResource } from "../../../.tmp-tests/features/embeddingIndexing/shared/pipelineState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("clears downstream references when the selected embedding bundle no longer exists", () => {
  const patch = clearMissingPipelineResource(
    {
      activeStage: "retrieval",
      selectedEmbeddingProfileId: "local-bge-m3-v1",
      selectedChunkBundleId: "chunk-bundle-1",
      activeEmbeddingRunId: "embedding-run-1",
      selectedEmbeddingBundleId: "embedding-bundle-1",
      activeIndexingRunId: "indexing-run-1",
      activeActivationRunId: "indexing-run-1",
      selectedRetrievalProfileId: "retrieval-profile-1",
    },
    "embeddingBundle",
  );

  assert.deepEqual(patch, {
    activeStage: "embedding",
    selectedEmbeddingBundleId: null,
    activeIndexingRunId: null,
    activeActivationRunId: null,
    selectedRetrievalProfileId: null,
  });
});

test("clears the stale indexing run and backs the workspace to indexing", () => {
  const patch = clearMissingPipelineResource(
    {
      activeStage: "retrieval",
      selectedEmbeddingProfileId: "local-bge-m3-v1",
      selectedChunkBundleId: "chunk-bundle-1",
      activeEmbeddingRunId: "embedding-run-1",
      selectedEmbeddingBundleId: "embedding-bundle-1",
      activeIndexingRunId: "indexing-run-1",
      activeActivationRunId: "indexing-run-1",
      selectedRetrievalProfileId: "retrieval-profile-1",
    },
    "indexingRun",
  );

  assert.deepEqual(patch, {
    activeStage: "indexing",
    activeIndexingRunId: null,
    activeActivationRunId: null,
  });
});

test("clears only the retrieval profile when that profile was deleted", () => {
  const patch = clearMissingPipelineResource(
    {
      activeStage: "retrieval",
      selectedEmbeddingProfileId: "local-bge-m3-v1",
      selectedChunkBundleId: "chunk-bundle-1",
      activeEmbeddingRunId: "embedding-run-1",
      selectedEmbeddingBundleId: "embedding-bundle-1",
      activeIndexingRunId: "indexing-run-1",
      activeActivationRunId: "indexing-run-1",
      selectedRetrievalProfileId: "retrieval-profile-1",
    },
    "retrievalProfile",
  );

  assert.deepEqual(patch, {
    activeStage: "activation",
    selectedRetrievalProfileId: null,
  });
});

