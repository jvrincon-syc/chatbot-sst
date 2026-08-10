import assert from "node:assert/strict";

import {
  loadRetrievalProfileStatus,
  loadRetrievalProfiles,
  searchRetrieval,
  validateRetrievalProfile,
} from "../../../.tmp-tests/features/retrieval/retrievalApi.js";

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

await test("loads retrieval profiles from the paginated contract", async () => {
  const calls = [];
  globalThis.fetch = async (input) => {
    calls.push(input);
    return jsonResponse({
      items: [
        {
          retrieval_profile_id: "retrieval-profile-1",
          consumer_scope_type: "chatbot",
          consumer_scope_id: "sst-default",
          embedding_profile_id: "local-bge-m3-v1",
          indexing_target_id: "target-1",
          lexical_fallback_policy: "allowed_when_vector_unavailable",
          active: true,
          validation_status: "passed",
          last_runtime_status: "ok",
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    });
  };

  const page = await loadRetrievalProfiles();
  assert.equal(calls[0], "/api/retrieval/profiles");
  assert.equal(page.items[0].retrievalProfileId, "retrieval-profile-1");
  assert.equal(page.items[0].validationStatus, "passed");
});

await test("loads profile status with runtime and readiness split", async () => {
  const calls = [];
  globalThis.fetch = async (input) => {
    calls.push(input);
    return jsonResponse({
      profile: {
        retrieval_profile_id: "retrieval-profile-1",
        validation_status: "passed",
        last_runtime_status: "ok",
        lexical_fallback_policy: "allowed_when_vector_unavailable",
      },
      runtime: {
        retrieval_profile_id: "retrieval-profile-1",
        query_engine_available: true,
        vector_retrieval_enabled: true,
        lexical_fallback_allowed: true,
        blocked_reason: null,
      },
      readiness: {
        retrieval_profile_id: "retrieval-profile-1",
        ready: true,
        active_vector_rows: 12,
        embedding_bundle_id: "embedding-bundle-1",
        blocking_reasons: [],
      },
    });
  };

  const status = await loadRetrievalProfileStatus("retrieval-profile-1");
  assert.equal(calls[0], "/api/retrieval/profiles/retrieval-profile-1/status");
  assert.equal(status.runtime.queryEngineAvailable, true);
  assert.equal(status.readiness.ready, true);
  assert.equal(status.readiness.activeVectorRows, 12);
});

await test("validates a retrieval profile without sending a user question", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      retrieval_profile_id: "retrieval-profile-1",
      status: "passed",
      validator_version: "retrieval-validator-v1",
      query_dimension: null,
      candidates_found: 3,
      blocking_reasons: [],
    });
  };

  const result = await validateRetrievalProfile("retrieval-profile-1");
  assert.equal(calls[0][0], "/api/retrieval/validate");
  const body = JSON.parse(calls[0][1].body);
  assert.deepEqual(body, { retrieval_profile_id: "retrieval-profile-1" });
  assert.equal(result.status, "passed");
  assert.equal(result.candidatesFound, 3);
});

await test("executes retrieval search and maps evidence items", async () => {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return jsonResponse({
      retrieval_profile_id: "retrieval-profile-1",
      top_k: 2,
      items: [
        {
          node_id: "node-1",
          document_id: "doc-1",
          parent_node_id: "parent-1",
          child_chunk_id: "child-1",
          text: "evidencia textual",
          score: 0.91,
          source: "vector",
          page_start: 3,
          page_end: 3,
          section_title: "Alcance",
          section_path: "Capitulo 1",
          metadata: { lane: "primary" },
          embedding_profile_id: "local-bge-m3-v1",
          corpus_version: "phase1-main",
          embedding_bundle_id: "embedding-bundle-1",
        },
      ],
    });
  };

  const result = await searchRetrieval({
    retrievalProfileId: "retrieval-profile-1",
    query: "alcance del procedimiento",
    topK: 2,
  });

  assert.equal(calls[0][0], "/api/retrieval/search");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    retrieval_profile_id: "retrieval-profile-1",
    query: "alcance del procedimiento",
    top_k: 2,
  });
  assert.equal(result.topK, 2);
  assert.equal(result.items[0].documentId, "doc-1");
  assert.equal(result.items[0].sectionTitle, "Alcance");
});
