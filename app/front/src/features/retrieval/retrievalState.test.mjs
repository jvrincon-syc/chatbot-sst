import assert from "node:assert/strict";

import { toRetrievalProfileStatus } from "../../../.tmp-tests/features/retrieval/retrievalMappers.js";
import {
  deriveRetrievalStageState,
  retrievalCanValidate,
} from "../../../.tmp-tests/features/retrieval/retrievalState.js";

function test(name, assertion) {
  try {
    assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("treats retrieval as unavailable before activation returns a retrieval profile id", () => {
  const state = deriveRetrievalStageState({
    retrievalProfileId: null,
    statusPayload: null,
  });

  assert.equal(state.stage, "unavailable");
});

test("exposes blocked reasons from retrieval profile status", () => {
  const status = toRetrievalProfileStatus({
    readiness: {
      ready: false,
      blocking_reasons: ["NO_ACTIVE_VECTOR_ROWS"],
    },
  });

  assert.deepEqual(status.readiness.blockingReasons, ["NO_ACTIVE_VECTOR_ROWS"]);
});

test("stays loading when a profile exists but status has not loaded", () => {
  const state = deriveRetrievalStageState({
    retrievalProfileId: "retrieval-profile-1",
    statusPayload: null,
  });

  assert.equal(state.stage, "loading");
});

test("marks the stage blocked and surfaces readiness reasons", () => {
  const status = toRetrievalProfileStatus({
    profile: { retrieval_profile_id: "retrieval-profile-1" },
    runtime: { retrieval_profile_id: "retrieval-profile-1", query_engine_available: true },
    readiness: {
      ready: false,
      blocking_reasons: ["RETRIEVAL_PROFILE_NOT_VALIDATED"],
    },
  });

  const state = deriveRetrievalStageState({
    retrievalProfileId: "retrieval-profile-1",
    statusPayload: status,
  });

  assert.equal(state.stage, "blocked");
  assert.deepEqual(state.blockingReasons, ["RETRIEVAL_PROFILE_NOT_VALIDATED"]);
});

test("marks the stage ready when readiness passes", () => {
  const status = toRetrievalProfileStatus({
    profile: { retrieval_profile_id: "retrieval-profile-1" },
    runtime: { retrieval_profile_id: "retrieval-profile-1", query_engine_available: true },
    readiness: { ready: true, blocking_reasons: [] },
  });

  const state = deriveRetrievalStageState({
    retrievalProfileId: "retrieval-profile-1",
    statusPayload: status,
  });

  assert.equal(state.stage, "ready");
});

test("allows validation only with a profile id and an available query engine", () => {
  const healthy = toRetrievalProfileStatus({
    profile: { retrieval_profile_id: "retrieval-profile-1" },
    runtime: { retrieval_profile_id: "retrieval-profile-1", query_engine_available: true },
    readiness: { ready: false, blocking_reasons: ["NO_ACTIVE_VECTOR_ROWS"] },
  });
  // Runtime healthy but readiness blocked: validation is still allowed because it
  // gates on runtime, not readiness.
  assert.equal(retrievalCanValidate(healthy), true);

  const engineDown = toRetrievalProfileStatus({
    profile: { retrieval_profile_id: "retrieval-profile-1" },
    runtime: { retrieval_profile_id: "retrieval-profile-1", query_engine_available: false },
    readiness: { ready: true, blocking_reasons: [] },
  });
  assert.equal(retrievalCanValidate(engineDown), false);

  const noProfile = toRetrievalProfileStatus({
    profile: { retrieval_profile_id: "" },
    runtime: { query_engine_available: true },
    readiness: { ready: true, blocking_reasons: [] },
  });
  assert.equal(retrievalCanValidate(noProfile), false);
});
