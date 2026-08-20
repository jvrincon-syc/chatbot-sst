import assert from "node:assert/strict";

import {
  buildRelease,
  createProject,
  listProjects,
  normalizeDocuments,
  updateProject,
  uploadDocument,
} from "../../../.tmp-tests/features/platform/platformApi.js";

async function test(name, assertion) {
  try {
    await assertion();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

function captureFetch(response) {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push([input, init]);
    return response;
  };
  return calls;
}

// --- Contrato de lectura: same-origin + query paginada --------------------- //

await test("listProjects hace GET same-origin con query paginada", async () => {
  const calls = captureFetch(jsonResponse({ items: [], page: 1, page_size: 25, total_items: 0, total_pages: 0 }));
  await listProjects({ page: 2, pageSize: 10 });
  const [url, init] = calls[0];
  assert.equal(url, "/api/platform/projects?page=2&page_size=10");
  assert.equal(init.method, undefined); // GET por defecto
  assert.equal(init.credentials, "same-origin");
});

// --- POST JSON ------------------------------------------------------------- //

await test("createProject hace POST JSON con el cuerpo tipado", async () => {
  const calls = captureFetch(jsonResponse({ project_id: "proj_demo" }));
  await createProject({ project_slug: "demo", display_name: "Demo" });
  const [url, init] = calls[0];
  assert.equal(url, "/api/platform/projects");
  assert.equal(init.method, "POST");
  assert.equal(init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(init.body), { project_slug: "demo", display_name: "Demo" });
});

// --- PATCH ----------------------------------------------------------------- //

await test("updateProject usa el verbo PATCH", async () => {
  const calls = captureFetch(jsonResponse({ project_id: "proj_demo" }));
  await updateProject("proj_demo", { display_name: "Nuevo" });
  const [url, init] = calls[0];
  assert.equal(url, "/api/platform/projects/proj_demo");
  assert.equal(init.method, "PATCH");
});

// --- Multipart: el browser pone el boundary; no seteamos Content-Type ------ //

await test("uploadDocument envía multipart sin Content-Type manual", async () => {
  const calls = captureFetch(jsonResponse({ source_document_revision_id: "srev_1" }));
  await uploadDocument("proj_demo", new Blob(["contenido"], { type: "text/markdown" }), "manuals/a.md");
  const [url, init] = calls[0];
  assert.equal(url, "/api/platform/projects/proj_demo/documents");
  assert.equal(init.method, "POST");
  assert.equal(init.body instanceof FormData, true);
  assert.equal(init.headers["Content-Type"], undefined);
  assert.equal(init.body.get("source_relpath"), "manuals/a.md");
});

// --- Idempotencia en mutaciones de release --------------------------------- //

await test("buildRelease adjunta un Idempotency-Key de plataforma", async () => {
  const calls = captureFetch(jsonResponse({ rag_release_id: "ragr_1", revisions_built: 0, reused_stages: 0, built_stages: 0 }));
  await buildRelease("ragr_1");
  const [, init] = calls[0];
  assert.equal(init.headers["Idempotency-Key"].startsWith("platform-"), true);
});

await test("buildRelease respeta una Idempotency-Key provista (replay)", async () => {
  const calls = captureFetch(jsonResponse({ rag_release_id: "ragr_1", revisions_built: 0, reused_stages: 0, built_stages: 0 }));
  await buildRelease("ragr_1", { idempotencyKey: "platform-fija" });
  const [, init] = calls[0];
  assert.equal(init.headers["Idempotency-Key"], "platform-fija");
});

// --- Envelope de error único: status y code preservados -------------------- //

for (const status of [401, 403, 409, 422, 503]) {
  await test(`el error HTTP ${status} se surface con status y code`, async () => {
    captureFetch(jsonResponse({ error: { code: `CODE_${status}`, message: "m" } }, { ok: false, status }));
    await assert.rejects(
      () => normalizeDocuments("proj_demo", { rag_variant_id: "ragv_x", document_revision_ids: ["srev_x"], force: false }),
      (error) => {
        assert.equal(error.status, status);
        assert.equal(error.code, `CODE_${status}`);
        return true;
      },
    );
  });
}
