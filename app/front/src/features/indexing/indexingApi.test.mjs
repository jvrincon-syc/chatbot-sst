import assert from "node:assert/strict";

import {
  activateIndexingRun,
  createIndexingRun,
  loadIndexingOverview,
  loadIndexingRunDocuments,
  loadIndexingRunErrors,
  loadIndexingRetrievalReadiness,
  loadIndexingTargets,
} from "../../../.tmp-tests/features/indexing/indexingApi.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

function jsonResponse(body, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    json: async () => body,
  };
}

await test("creates an indexing run with only the embedding bundle id and idempotency", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      run_id: "indexing-run-1",
      profile_id: "local-bge-m3-v1",
      status: "pending",
      embedding_bundle_id: "embedding-bundle-1",
      validation_status: "pending",
      activation_status: "pending",
      summary: { requested_documents: 1, committed_documents: 0 },
      warnings: [],
      links: {
        self: "/api/indexing/runs/indexing-run-1",
        documents: "/api/indexing/runs/indexing-run-1/documents",
        errors: "/api/indexing/runs/indexing-run-1/errors",
        retrieval_readiness: "/api/indexing/runs/indexing-run-1/retrieval-readiness",
      },
    });
  };

  const run = await createIndexingRun(
    { embeddingBundleId: "embedding-bundle-1" },
    { idempotencyKey: "indexing-test-key" },
  );

  assert.equal(calls[0][0], "/api/indexing/runs");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "indexing-test-key");
  assert.deepEqual(JSON.parse(calls[0][1].body), { embedding_bundle_id: "embedding-bundle-1" });
  assert.equal(run.runId, "indexing-run-1");
  assert.equal(run.activationStatus, "pending");
});

await test("does not send consumer scope in activation requests", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      run_id: "indexing-run-1",
      embedding_bundle_id: "embedding-bundle-1",
      indexing_target_id: "target-1",
      retrieval_profile_id: "retrieval-profile-1",
      activated_rows: 12,
    });
  };

  const result = await activateIndexingRun({
    runId: "indexing-run-1",
    lexicalFallbackPolicy: "allowed_when_vector_unavailable",
  });

  assert.equal(calls[0][0], "/api/indexing/activations");
  const body = JSON.parse(calls[0][1].body);
  assert.deepEqual(body, {
    run_id: "indexing-run-1",
    lexical_fallback_policy: "allowed_when_vector_unavailable",
  });
  assert.equal("consumer_scope_type" in body, false);
  assert.equal("consumer_scope_id" in body, false);
  assert.equal(result.retrievalProfileId, "retrieval-profile-1");
});

await test("loads overview, targets, documents, errors and readiness", async () => {
  const queue = [
    jsonResponse({
      targets: 7,
      active_targets: 7,
      profiles: 7,
      verified_profiles: 0,
      sealed_bundles: 0,
      runs: 0,
      completed_runs: 0,
      active_runs: 0,
      bundle_first_enabled: true,
    }),
    jsonResponse({
      items: [
        {
          indexing_target_id: "target-idx-vec-local-bge-m3-v1",
          postgres_schema: "public",
          vector_table: "idx_vec_local_bge_m3_v1",
          distance_ops: "vector_cosine_ops",
          storage_schema_version: "idx-vec-v1",
          active: true,
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      items: [
        {
          document_id: "doc_1",
          source_relpath: "copasst/comunicacion.md",
          status: "committed",
          eligibility_status: "included",
          eligibility_reason: "embedding_bundle_ready",
          embedding_bundle_id: "embedding-bundle-1",
          parent_count: 1,
          child_count: 1,
          vector_count: 1,
          committed_at: "2026-08-06T00:00:00+00:00",
          error_code: null,
          internal_error_id: null,
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      items: [
        {
          document_id: "doc_2",
          status: "failed",
          error_code: "EMBEDDING_BUNDLE_STALE",
          internal_error_id: "a1b2",
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      run_id: "indexing-run-1",
      embedding_bundle_id: "embedding-bundle-1",
      indexing_target_id: "target-1",
      corpus_version: "phase1-main",
      ready: false,
      active_vector_rows: 0,
      blocking_reasons: ["INDEXING_BUNDLE_NOT_ACTIVATED"],
    }),
  ];
  const calls = [];
  globalThis.fetch = async (input) => {
    calls.push(input);
    return queue.shift();
  };

  const overview = await loadIndexingOverview();
  const targets = await loadIndexingTargets();
  const documents = await loadIndexingRunDocuments("indexing-run-1", { page: 1 });
  const errors = await loadIndexingRunErrors("indexing-run-1");
  const readiness = await loadIndexingRetrievalReadiness("indexing-run-1");

  assert.equal(calls[0], "/api/indexing/overview");
  assert.equal(overview.bundleFirstEnabled, true);
  assert.equal(calls[1], "/api/indexing/targets");
  assert.equal(targets.items[0].vectorTable, "idx_vec_local_bge_m3_v1");
  assert.equal(calls[2], "/api/indexing/runs/indexing-run-1/documents?page=1");
  assert.equal(documents.items[0].committedAt, "2026-08-06T00:00:00+00:00");
  assert.equal(errors.items[0].internalErrorId, "a1b2");
  assert.deepEqual(readiness.blockingReasons, ["INDEXING_BUNDLE_NOT_ACTIVATED"]);
});
