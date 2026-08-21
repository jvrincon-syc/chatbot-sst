import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Regresión de seguridad/contrato (Task 13, frontend). Ejercita el cliente REAL
// (`platformApi` sin mockear) con `fetch` stubbeado para auditar el body/headers
// que efectivamente salen a la red: ninguna mutación puede filtrar autoridad
// física (actor/target/tabla/ruta) ni salirse del contrato de Fase 7.
import {
  buildRelease,
  createCorpusSnapshot,
  createReleaseDraft,
  createVariant,
  normalizeDocuments,
  publishRelease,
  retireRelease,
  uploadDocument,
  validateRelease,
} from "./platformApi.js";
import {
  readPlatformPreferences,
  writePlatformPreferences,
} from "./platformPersistence.js";
import { DEFAULT_PLATFORM_PREFERENCES } from "./platformState.js";

// Claves que el frontend NUNCA debe enviar (invariantes de Fase 7).
const FORBIDDEN_KEYS = [
  "actor_id",
  "indexing_target_id",
  "indexing_target",
  "target_bindings",
  "table_name",
  "physical_path",
  "bearer",
  "token",
];

function okResponse(payload: unknown = {}) {
  // Fake mínimo que satisface readJsonResponse (usa .text()) + readJson (.ok).
  return {
    ok: true,
    status: 200,
    text: async () => JSON.stringify(payload),
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  window.localStorage.clear();
  fetchMock = vi.fn(async () => okResponse({}));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

type Init = { body?: unknown; headers?: Record<string, string> };

function callAt(index: number): { url: string; init: Init } {
  const [url, init] = fetchMock.mock.calls[index] as [string, Init];
  return { url, init };
}

function jsonBodyAt(index: number): Record<string, unknown> {
  const { init } = callAt(index);
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

function assertNoForbiddenKeys(body: Record<string, unknown>): void {
  for (const key of FORBIDDEN_KEYS) {
    expect(key in body, `body no debe contener ${key}`).toBe(false);
  }
}

describe("platform contract guards — request bodies", () => {
  it("createVariant envía EXCLUSIVAMENTE cell_id + variant_slug", async () => {
    await createVariant("proj_x", { cell_id: "cell_1", variant_slug: "v1" });
    const body = jsonBodyAt(0);
    expect(Object.keys(body).sort()).toEqual(["cell_id", "variant_slug"]);
    assertNoForbiddenKeys(body);
  });

  it("normalizeDocuments va por rag_variant_id, sin processing_profile_id ni target físico", async () => {
    await normalizeDocuments("proj_x", {
      rag_variant_id: "ragv_1",
      document_revision_ids: ["srev_1"],
      force: false,
    });
    const body = jsonBodyAt(0);
    expect(Object.keys(body).sort()).toEqual([
      "document_revision_ids",
      "force",
      "rag_variant_id",
    ]);
    expect("processing_profile_id" in body).toBe(false);
    assertNoForbiddenKeys(body);
  });

  it("createReleaseDraft usa target_binding_key lógica, nunca un target físico", async () => {
    await createReleaseDraft({
      corpus_snapshot_id: "corpus_1",
      rag_variant_id: "ragv_1",
      target_binding_key: "primary",
    });
    const body = jsonBodyAt(0);
    expect(Object.keys(body).sort()).toEqual([
      "corpus_snapshot_id",
      "rag_variant_id",
      "target_binding_key",
    ]);
    assertNoForbiddenKeys(body);
  });

  it("createCorpusSnapshot no filtra autoridad física", async () => {
    await createCorpusSnapshot({
      project_id: "proj_x",
      document_revision_ids: ["srev_1"],
    });
    const body = jsonBodyAt(0);
    expect(body.project_id).toBe("proj_x");
    assertNoForbiddenKeys(body);
  });

  it("retireRelease envía solo { reason }", async () => {
    await retireRelease("ragr_1", { reason: "obsoleta" });
    const body = jsonBodyAt(0);
    expect(Object.keys(body)).toEqual(["reason"]);
    assertNoForbiddenKeys(body);
  });

  it("upload solo lleva file + source_relpath (el servidor calcula hash/target)", async () => {
    const file = new File(["x"], "a.pdf", { type: "application/pdf" });
    await uploadDocument("proj_x", file, "manuales/a.pdf");
    const { init } = callAt(0);
    const form = init.body as FormData;
    expect(Array.from(form.keys()).sort()).toEqual(["file", "source_relpath"]);
    for (const key of FORBIDDEN_KEYS) {
      expect(form.has(key)).toBe(false);
    }
  });
});

describe("platform contract guards — idempotency plumbing", () => {
  it("las 4 mutaciones de release adjuntan Idempotency-Key y reusan la que se pasa", async () => {
    await buildRelease("ragr_1", { idempotencyKey: "platform-key-A" });
    await validateRelease("ragr_1", { idempotencyKey: "platform-key-A" });
    await publishRelease("ragr_1", { idempotencyKey: "platform-key-B" });
    await retireRelease("ragr_1", { reason: "x" }, { idempotencyKey: "platform-key-B" });

    // Misma intención lógica → misma key verbatim (el hook la mantiene estable).
    expect(callAt(0).init.headers?.["Idempotency-Key"]).toBe("platform-key-A");
    expect(callAt(1).init.headers?.["Idempotency-Key"]).toBe("platform-key-A");
    // Nueva intención → key distinta.
    expect(callAt(2).init.headers?.["Idempotency-Key"]).toBe("platform-key-B");
    expect(callAt(3).init.headers?.["Idempotency-Key"]).toBe("platform-key-B");
  });

  it("createReleaseDraft NO adjunta Idempotency-Key (no es una de las 4 del lifecycle)", async () => {
    await createReleaseDraft({
      corpus_snapshot_id: "corpus_1",
      rag_variant_id: "ragv_1",
      target_binding_key: "primary",
    });
    expect(callAt(0).init.headers?.["Idempotency-Key"]).toBeUndefined();
  });
});

describe("platform contract guards — persistencia aislada del legacy", () => {
  it("solo persiste los 4 IDs de navegación; nunca bearer/token/target", () => {
    writePlatformPreferences({
      ...DEFAULT_PLATFORM_PREFERENCES,
      selectedProjectId: "proj_x",
      selectedRagReleaseId: "ragr_1",
    });
    const stored = readPlatformPreferences();
    expect(Object.keys(stored).sort()).toEqual([
      "selectedCorpusSnapshotId",
      "selectedProjectId",
      "selectedRagReleaseId",
      "selectedRagVariantId",
    ]);
    for (const key of ["bearer", "token", "indexing_target_id", "target_bindings"]) {
      expect(key in stored).toBe(false);
    }
  });

  it("escribir preferencias de plataforma no toca la clave del dashboard legacy", () => {
    writePlatformPreferences({ ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId: "proj_x" });
    // El legacy usa su propia clave versionada (D6); la plataforma no la contamina.
    expect(window.localStorage.getItem("chatbot-sst.dashboard.preferences.v2")).toBeNull();
    expect(window.localStorage.getItem("chatbot-sst.platform.preferences.v1")).not.toBeNull();
  });
});
