import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CorpusSnapshotWorkspace } from "./CorpusSnapshotWorkspace.js";
import { readPlatformPreferences, writePlatformPreferences } from "../platformPersistence.js";
import { DEFAULT_PLATFORM_PREFERENCES } from "../platformState.js";
import * as platformApi from "../platformApi.js";
import type {
  CorpusSnapshot,
  ProjectDocumentRevision,
} from "../platformTypes.js";

// Cliente HTTP mockeado en el límite de red: ningún test toca fetch.
vi.mock("../platformApi.js", () => ({
  listAllDocuments: vi.fn(),
  listAllCorpusSnapshots: vi.fn(),
  createCorpusSnapshot: vi.fn(),
}));

const api = vi.mocked(platformApi);

function makeRevision(overrides: Partial<ProjectDocumentRevision> = {}): ProjectDocumentRevision {
  return {
    source_document_revision_id: "srev_1",
    logical_document_id: "ldoc_1",
    source_relpath: "manuales/proc.pdf",
    file_size: 1024,
    raw_registered: true,
    normalized_registered: true,
    review_state: "processed",
    processing_status: "normalized",
    uploaded_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeSnapshot(overrides: Partial<CorpusSnapshot> = {}): CorpusSnapshot {
  return {
    corpus_snapshot_id: "corpus_new",
    project_id: "proj_alpha",
    manifest_hash: "sha256:abcd",
    document_count: 1,
    documents: [],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function selectProjectInStorage(projectId: string): void {
  writePlatformPreferences({ ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId: projectId });
}

beforeEach(() => {
  window.localStorage.clear();
  api.listAllDocuments.mockResolvedValue([]);
  api.listAllCorpusSnapshots.mockResolvedValue([]);
  api.createCorpusSnapshot.mockResolvedValue(makeSnapshot());
});

describe("CorpusSnapshotWorkspace", () => {
  it("renderiza las revisiones normalizadas candidatas con sus IDs", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);

    render(<CorpusSnapshotWorkspace />);

    expect(await screen.findByText("srev_1")).toBeTruthy();
    expect(screen.getByText("ldoc_1")).toBeTruthy();
  });

  it("crea un snapshot de revisiones processed sin eligibility_decisions", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);

    const user = userEvent.setup();
    render(<CorpusSnapshotWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Incluir revisión srev_1/ }),
    );
    await user.click(screen.getByRole("button", { name: /Crear snapshot/ }));

    await waitFor(() => expect(api.createCorpusSnapshot).toHaveBeenCalledTimes(1));
    const body = api.createCorpusSnapshot.mock.calls[0][0];
    expect(body.project_id).toBe("proj_alpha");
    expect(body.document_revision_ids).toEqual(["srev_1"]);
    // Una revisión processed no manda decisión: `not_required` es implícito server-side.
    expect("eligibility_decisions" in body).toBe(false);
  });

  it("exige decisión explícita para una revisión needs_review antes de crear", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision({ review_state: "needs_review" })]);

    const user = userEvent.setup();
    render(<CorpusSnapshotWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Incluir revisión srev_1/ }),
    );
    // Sin decisión, Crear está deshabilitado (gate fail-closed cliente).
    expect(screen.getByRole("button", { name: /Crear snapshot/ })).toHaveProperty(
      "disabled",
      true,
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: /Decisión de elegibilidad para srev_1/ }),
      "approved_after_review",
    );
    const createButton = screen.getByRole("button", { name: /Crear snapshot/ });
    expect(createButton).toHaveProperty("disabled", false);

    await user.click(createButton);
    await waitFor(() => expect(api.createCorpusSnapshot).toHaveBeenCalledTimes(1));
    const body = api.createCorpusSnapshot.mock.calls[0][0];
    expect(body.eligibility_decisions).toEqual({ srev_1: "approved_after_review" });
  });

  it("tras crear, persiste solo el corpus_snapshot_id y refresca el historial", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);

    const user = userEvent.setup();
    render(<CorpusSnapshotWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Incluir revisión srev_1/ }),
    );
    await user.click(screen.getByRole("button", { name: /Crear snapshot/ }));

    await waitFor(() =>
      expect(readPlatformPreferences().selectedCorpusSnapshotId).toBe("corpus_new"),
    );
    // El historial se recarga tras crear (segunda llamada al helper plano).
    await waitFor(() => expect(api.listAllCorpusSnapshots.mock.calls.length).toBeGreaterThan(1));
    // No se filtró nada sensible: solo el ID de navegación.
    const stored = readPlatformPreferences();
    expect(Object.keys(stored)).not.toContain("manifest_hash");
  });

  it("sin proyecto muestra estado vacío direccional y no llama a la API", async () => {
    render(<CorpusSnapshotWorkspace />);

    expect(
      await screen.findByText(/Selecciona un proyecto para construir un snapshot/),
    ).toBeTruthy();
    expect(api.listAllDocuments).not.toHaveBeenCalled();
    expect(api.listAllCorpusSnapshots).not.toHaveBeenCalled();
  });

  it("ante 409 cross-project surfacea un mensaje fail-closed", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);
    api.createCorpusSnapshot.mockRejectedValue({
      status: 409,
      code: "REVISION_PROJECT_MISMATCH",
    });

    const user = userEvent.setup();
    render(<CorpusSnapshotWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Incluir revisión srev_1/ }),
    );
    await user.click(screen.getByRole("button", { name: /Crear snapshot/ }));

    expect(await screen.findByText(/inválida o pertenece a otro proyecto/)).toBeTruthy();
  });

  it("selecciona en bloque solo las revisiones elegibles sin auto-incluir needs_review", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([
      makeRevision({ source_document_revision_id: "srev_1", review_state: "processed" }),
      makeRevision({
        source_document_revision_id: "srev_2",
        logical_document_id: "ldoc_2",
        review_state: "needs_review",
      }),
    ]);

    const user = userEvent.setup();
    render(<CorpusSnapshotWorkspace />);

    await user.click(
      await screen.findByRole("button", { name: "Seleccionar todas las elegibles" }),
    );

    expect(screen.getByText("1 de 2 seleccionadas")).toBeTruthy();
    const checkboxes = screen.getAllByRole("checkbox", { name: /Incluir revisión/ });
    expect((checkboxes[0] as HTMLInputElement).checked).toBe(true);
    expect((checkboxes[1] as HTMLInputElement).checked).toBe(false);
  });
});
