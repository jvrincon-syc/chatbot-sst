import assert from "node:assert/strict";

import {
  toActivationRequest,
  toIndexingRun,
  toIndexingRunDocument,
  toIndexingRunRequest,
} from "../../../.tmp-tests/features/indexing/indexingMappers.js";
import {
  canActivateIndexingRun,
  indexingDocumentIsCommitted,
  indexingRunIsPartial,
  indexingRunIsTerminal,
  indexingRunProgressPercent,
} from "../../../.tmp-tests/features/indexing/indexingState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("builds indexing run requests from only the embedding bundle id", () => {
  assert.deepEqual(toIndexingRunRequest("embedding-bundle-1"), {
    embedding_bundle_id: "embedding-bundle-1",
  });
});

test("does not include consumer scope in activation requests", () => {
  assert.deepEqual(toActivationRequest("indexing-run-1"), {
    run_id: "indexing-run-1",
    lexical_fallback_policy: "allowed_when_vector_unavailable",
  });
});

test("honors an explicit lexical fallback policy without adding scope", () => {
  const request = toActivationRequest("indexing-run-1", "never");
  assert.deepEqual(request, {
    run_id: "indexing-run-1",
    lexical_fallback_policy: "never",
  });
  assert.equal("consumer_scope_type" in request, false);
  assert.equal("consumer_scope_id" in request, false);
});

test("allows activation only for a completed run with pending activation", () => {
  const base = toIndexingRun({
    run_id: "indexing-run-1",
    status: "completed",
    activation_status: "pending",
    summary: { requested_documents: 1, committed_documents: 1 },
  });
  assert.equal(canActivateIndexingRun(base), true);

  const running = toIndexingRun({ run_id: "r", status: "running", activation_status: "pending" });
  assert.equal(canActivateIndexingRun(running), false);

  const alreadyActive = toIndexingRun({
    run_id: "r",
    status: "completed",
    activation_status: "active",
  });
  assert.equal(canActivateIndexingRun(alreadyActive), false);
});

test("treats completed, failed, cancelled and blocked as terminal", () => {
  assert.equal(indexingRunIsTerminal("completed"), true);
  assert.equal(indexingRunIsTerminal("failed"), true);
  assert.equal(indexingRunIsTerminal("cancelled"), true);
  assert.equal(indexingRunIsTerminal("blocked"), true);
  assert.equal(indexingRunIsTerminal("pending"), false);
  assert.equal(indexingRunIsTerminal("running"), false);
});

test("detects partially completed runs from committed documents", () => {
  const partial = toIndexingRun({
    run_id: "r",
    status: "failed",
    summary: { requested_documents: 3, committed_documents: 1 },
  });
  assert.equal(indexingRunIsPartial(partial), true);

  const cleanFail = toIndexingRun({
    run_id: "r",
    status: "failed",
    summary: { requested_documents: 3, committed_documents: 0 },
  });
  assert.equal(indexingRunIsPartial(cleanFail), false);
});

test("counts a document as indexed only when committed_at is present", () => {
  const committed = toIndexingRunDocument({
    document_id: "doc_1",
    status: "committed",
    committed_at: "2026-08-06T00:00:00+00:00",
  });
  assert.equal(indexingDocumentIsCommitted(committed), true);

  const running = toIndexingRunDocument({ document_id: "doc_2", status: "running" });
  assert.equal(indexingDocumentIsCommitted(running), false);
});

test("computes run progress from committed and requested documents", () => {
  assert.equal(
    indexingRunProgressPercent({ requestedDocuments: 4, committedDocuments: 1 }),
    25,
  );
  assert.equal(
    indexingRunProgressPercent({ requestedDocuments: 0, committedDocuments: 0 }),
    0,
  );
});
