import assert from "node:assert/strict";

import { mapPipelineError } from "../../../.tmp-tests/shared/api/errorMapping.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

// Preservación: el envelope del backend (code/message/details/status) nunca se
// pierde ni se aplana a un genérico cuando viene presente.
await test("preserves backend code, message, status and details", async () => {
  const mapped = mapPipelineError({
    status: 422,
    code: "INVALID_PLATFORM_ID",
    message: "id inválido",
    details: { field: "project_id" },
    run_id: "run_9",
  });
  assert.equal(mapped.status, 422);
  assert.equal(mapped.code, "INVALID_PLATFORM_ID");
  assert.equal(mapped.message, "id inválido");
  assert.deepEqual(mapped.details, { field: "project_id" });
  assert.equal(mapped.runId, "run_9");
  assert.equal(mapped.retryable, false);
});

// Fail-closed: un 503 terminal (feature apagada / auth mal configurada) NO es
// retryable aunque sea 503; ofrecer retry sería un loop que nunca succeede.
await test("terminal 503 codes are not retryable", async () => {
  for (const code of [
    "RAG_PLATFORM_V1_DISABLED",
    "RETRIEVAL_V1_DISABLED",
    "HTTP_AUTH_NOT_CONFIGURED",
  ]) {
    const mapped = mapPipelineError({ status: 503, code });
    assert.equal(mapped.retryable, false, `${code} debe ser terminal`);
    assert.equal(mapped.code, code, "el code se preserva");
  }
});

// Un 503 transitorio sin code terminal sí es retryable.
await test("transient 503/429 remain retryable", async () => {
  assert.equal(mapPipelineError({ status: 503, code: "POSTGRES_UNAVAILABLE" }).retryable, true);
  assert.equal(mapPipelineError({ status: 429, code: "RATE_LIMITED" }).retryable, true);
});

// Conflictos de contrato/estado (409) nunca son retryables automáticamente.
await test("409 conflicts are not retryable", async () => {
  for (const code of [
    "STALE_VARIANT_MATRIX_CELL",
    "INVALID_RELEASE_TRANSITION",
    "IDEMPOTENCY_KEY_CONFLICT",
  ]) {
    assert.equal(mapPipelineError({ status: 409, code }).retryable, false, code);
  }
});

// Error desconocido: se conserva el mensaje si es string, sin inventar éxito.
await test("unknown errors fall back without losing information", async () => {
  const mapped = mapPipelineError("boom");
  assert.equal(mapped.code, "PIPELINE_UNKNOWN_ERROR");
  assert.equal(mapped.message, "boom");
  assert.equal(mapped.retryable, false);
});
