import assert from "node:assert/strict";

import {
  loadRetrievalProfileStatus,
  loadRetrievalProfiles,
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
