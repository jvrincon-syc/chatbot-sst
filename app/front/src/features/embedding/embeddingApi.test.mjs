import assert from "node:assert/strict";

import {
  buildQuery,
  createIdempotencyKey,
} from "../../../.tmp-tests/features/embeddingIndexing/shared/apiClient.js";
import { mapPipelineError } from "../../../.tmp-tests/features/embeddingIndexing/shared/errorMapping.js";
import {
  createEmbeddingRun,
  loadChunkBundles,
  loadEmbeddingBundle,
  loadEmbeddingBundleChunks,
  loadEmbeddingIndexingReadiness,
  loadEmbeddingProfiles,
} from "../../../.tmp-tests/features/embedding/embeddingApi.js";

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

// --- Task 2: shared api utilities ---

await test("creates snake_case query strings and preserves page params", () => {
  assert.equal(
    buildQuery({ page: 2, page_size: 25, profile_id: "local-bge-m3-v1" }),
    "?page=2&page_size=25&profile_id=local-bge-m3-v1",
  );
});

await test("drops null and undefined query params", () => {
  assert.equal(buildQuery({ page: 1, page_size: null, profile_id: undefined }), "?page=1");
  assert.equal(buildQuery({ page: null, page_size: undefined }), "");
});

await test("maps IDEMPOTENCY_CONFLICT to a stable ui code", () => {
  const mapped = mapPipelineError({
    status: 409,
    code: "IDEMPOTENCY_CONFLICT",
    message: "request fingerprint differs",
    runId: "run-1",
  });

  assert.equal(mapped.code, "IDEMPOTENCY_CONFLICT");
  assert.equal(mapped.retryable, false);
  assert.equal(mapped.runId, "run-1");
  assert.equal(mapped.message, "request fingerprint differs");
});

await test("marks busy executor errors as retryable", () => {
  const mapped = mapPipelineError({
    status: 429,
    code: "EMBEDDING_EXECUTOR_BUSY",
    message: "executor busy",
  });
  assert.equal(mapped.retryable, true);
});

await test("creates prefixed idempotency keys", () => {
  const key = createIdempotencyKey("embedding");
  assert.equal(key.startsWith("embedding-"), true);
});

// --- Task 3: embedding api ---

await test("loads embedding profiles from the paginated contract", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      items: [
        {
          profile_id: "local-bge-m3-v1",
          provider: "bge",
          model: "BAAI/bge-m3",
          dimension: 1024,
          active: true,
          document_enabled: false,
          can_embed_documents: false,
          compatibility_status: "compatibility_not_proven",
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    });
  };

  const page = await loadEmbeddingProfiles();
  assert.equal(calls[0][0], "/api/embedding/profiles");
  assert.equal(page.items[0].profileId, "local-bge-m3-v1");
  assert.equal(page.items[0].canEmbedDocuments, false);
  assert.equal(page.totalItems, 1);
});

await test("creates an embedding run with idempotency and snake_case payload", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      embedding_run_id: "embedding-run-1",
      status: "pending",
      source_chunk_bundle_id: "chunk-bundle-1",
      embedding_profile_id: "local-bge-m3-v1",
      summary: { requested_children: 12, embedded_children: 0 },
      warnings: [],
      produced_embedding_bundle_id: null,
      links: { self: "/api/embedding/runs/embedding-run-1" },
    });
  };

  const run = await createEmbeddingRun(
    { chunkBundleId: "chunk-bundle-1", profileId: "local-bge-m3-v1" },
    { idempotencyKey: "embedding-test-key" },
  );

  assert.equal(calls[0][0], "/api/embedding/runs");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "embedding-test-key");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    chunk_bundle_id: "chunk-bundle-1",
    profile_id: "local-bge-m3-v1",
  });
  assert.equal(run.embeddingRunId, "embedding-run-1");
  assert.equal(run.summary.requestedChildren, 12);
});

await test("loads chunk bundles, embedding bundle, chunks and readiness", async () => {
  const queue = [
    jsonResponse({
      items: [
        {
          chunk_bundle_id: "chunk-bundle-1",
          bundle_fingerprint: "chunk-bundle-1",
          profile_id: "local-structural-v1",
          corpus_version: "phase1-main",
          source_document_id: "doc_1",
          parent_count: 1,
          child_count: 1,
          status: "legacy_unverified",
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      embedding_bundle_id: "embedding-bundle-1",
      source_chunk_bundle_id: "chunk-bundle-1",
      embedding_profile_id: "local-bge-m3-v1",
      dimension: 1024,
      vector_count: 12,
      checksums: { "vectors.npy": "abc" },
      status: "sealed",
      validation_status: "passed",
      readiness_status: "ready",
      links: {
        self: "/api/embedding/bundles/embedding-bundle-1",
        chunks: "/api/embedding/bundles/embedding-bundle-1/chunks",
        validation: "/api/embedding/bundles/embedding-bundle-1/validation",
        indexing_readiness: "/api/embedding/bundles/embedding-bundle-1/indexing-readiness",
      },
    }),
    jsonResponse({
      items: [
        {
          child_chunk_id: "child-1",
          parent_chunk_id: "parent-1",
          document_id: "doc_1",
          vector_offset: 0,
          vector_length: 1024,
          vector_checksum: "abc",
          content_hash: "def",
          chunk_ordinal: 0,
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      embedding_bundle_id: "embedding-bundle-1",
      indexing_target_id: "target-idx-vec-local-bge-m3-v1",
      status: "ready",
      blocking_reasons: [],
    }),
  ];
  const calls = [];
  globalThis.fetch = async (input) => {
    calls.push(input);
    return queue.shift();
  };

  const bundles = await loadChunkBundles();
  const bundle = await loadEmbeddingBundle("embedding-bundle-1");
  const chunks = await loadEmbeddingBundleChunks("embedding-bundle-1", { page: 1 });
  const readiness = await loadEmbeddingIndexingReadiness("embedding-bundle-1");

  assert.equal(calls[0], "/api/embedding/chunk-bundles");
  assert.equal(bundles.items[0].chunkBundleId, "chunk-bundle-1");
  assert.equal(bundle.links.chunks, "/api/embedding/bundles/embedding-bundle-1/chunks");
  assert.equal(bundle.readinessStatus, "ready");
  assert.equal(calls[2], "/api/embedding/bundles/embedding-bundle-1/chunks?page=1");
  assert.equal(chunks.items[0].childChunkId, "child-1");
  assert.equal(chunks.items[0].vectorLength, 1024);
  assert.equal(readiness.blockingReasons.length, 0);
});

await test("propagates the error envelope as a pipeline http error", async () => {
  globalThis.fetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({
      error: {
        code: "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN",
        message: "profile is not enabled for document embedding",
        run_id: null,
        details: {},
      },
    }),
  });

  let caught = null;
  try {
    await createEmbeddingRun(
      { chunkBundleId: "chunk-bundle-1", profileId: "local-bge-m3-v1" },
      { idempotencyKey: "k" },
    );
  } catch (error) {
    caught = error;
  }

  assert.notEqual(caught, null);
  const mapped = mapPipelineError(caught);
  assert.equal(mapped.code, "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN");
  assert.equal(mapped.status, 409);
  assert.equal(mapped.retryable, false);
});
