import assert from "node:assert/strict";

import {
  createChunkingRun,
  loadChunkingChildren,
  loadChunkingParents,
  loadChunkingProfiles,
  loadChunkingRunDocuments,
} from "../../../.tmp-tests/features/chunking/chunkingApi.js";

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

await test("loads chunking profiles from the HTTP contract", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse([
      {
        profile_id: "local-structural-v1",
        child_min_tokens: 250,
        child_target_tokens: 350,
        child_max_tokens: 450,
        overlap_ratio: 0.12,
        overlap_min_tokens: 30,
        overlap_max_tokens: 60,
      },
    ]);
  };

  const profiles = await loadChunkingProfiles();
  assert.equal(calls[0][0], "/api/chunking/profiles");
  assert.equal(profiles[0].profileId, "local-structural-v1");
  assert.equal(profiles[0].childTargetTokens, 350);
});

await test("creates a chunking run with idempotency and snake_case payload", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      run_id: "run_123",
      status: "queued",
      profile_id: "local-structural-v1",
      requested_documents: 2,
      completed_documents: 0,
      warnings: [],
      links: {
        self: "/api/chunking/runs/run_123",
        documents: "/api/chunking/runs/run_123/documents",
        validation: "/api/chunking/runs/run_123/validation",
      },
    });
  };

  const run = await createChunkingRun({
    idempotencyKey: "chunking-test-key",
    request: {
      scope: "documents",
      documentIds: ["doc_1", "doc_2"],
      profileId: "local-structural-v1",
      force: false,
    },
  });

  assert.equal(calls[0][0], "/api/chunking/runs");
  assert.equal(calls[0][1].headers["Idempotency-Key"], "chunking-test-key");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    scope: "documents",
    document_ids: ["doc_1", "doc_2"],
    profile_id: "local-structural-v1",
    force: false,
  });
  assert.equal(run.runId, "run_123");
  assert.equal(run.requestedDocuments, 2);
});

await test("loads paginated run documents, parents and children", async () => {
  const queue = [
    jsonResponse({
      items: [
        {
          document_id: "doc_1",
          status: "completed",
          reused: false,
          run_id: "run_1",
          normalized_relpath: "docs/doc_1.md",
        },
      ],
      page: 2,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
    jsonResponse({
      items: [
        {
          chunk_id: "parent_1",
          document_id: "doc_1",
          profile_id: "local-structural-v1",
          ordinal: 1,
          text: "Parent text",
          source_span: { page_start: 1, page_end: 2, char_start: 0, char_end: 40 },
          block_ids: ["block_1"],
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
          chunk_id: "child_1",
          document_id: "doc_1",
          profile_id: "local-structural-v1",
          parent_id: "parent_1",
          ordinal: 1,
          context_prefix: "ctx",
          text: "Child text",
          source_span: { page_start: 1, page_end: 1, char_start: 0, char_end: 20 },
          token_start: 0,
          token_end: 20,
          token_count: 20,
          overlap_previous_tokens: 0,
          overlap_next_tokens: 0,
          overlap_previous_span: null,
          overlap_next_span: null,
          zero_overlap_reasons: [],
          warnings: [],
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    }),
  ];

  globalThis.fetch = async (input) => {
    assert.equal(typeof input, "string");
    return queue.shift();
  };

  const documents = await loadChunkingRunDocuments({ runId: "run_1", page: 2 });
  const parents = await loadChunkingParents({ documentId: "doc_1", runId: "run_1" });
  const children = await loadChunkingChildren({ parentId: "parent_1" });

  assert.equal(documents.items[0].normalizedRelpath, "docs/doc_1.md");
  assert.equal(parents.items[0].chunkId, "parent_1");
  assert.equal(children.items[0].parentId, "parent_1");
});
