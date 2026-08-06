import assert from "node:assert/strict";

import {
  pipelineStageOrder,
  shouldContinuePolling,
} from "../../../.tmp-tests/features/embeddingIndexing/shared/pipelineFlow.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("shows activation as a distinct stage between indexing and retrieval", () => {
  assert.deepEqual(pipelineStageOrder(), [
    "embedding",
    "indexing",
    "activation",
    "retrieval",
  ]);
});

test("stops embedding polling when the run reaches a terminal state", () => {
  assert.equal(shouldContinuePolling("embedding", "completed"), false);
  assert.equal(shouldContinuePolling("embedding", "failed"), false);
  assert.equal(shouldContinuePolling("embedding", "cancelled"), false);
  assert.equal(shouldContinuePolling("embedding", "blocked"), false);
  assert.equal(shouldContinuePolling("embedding", "running"), true);
  assert.equal(shouldContinuePolling("embedding", "pending"), true);
});

test("stops indexing polling on terminal states too", () => {
  assert.equal(shouldContinuePolling("indexing", "completed"), false);
  assert.equal(shouldContinuePolling("indexing", "running"), true);
});
