import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DocumentIntakeWorkspace } from "./DocumentIntakeWorkspace.js";
import { writePlatformPreferences } from "../platformPersistence.js";
import { DEFAULT_PLATFORM_PREFERENCES } from "../platformState.js";
import * as platformApi from "../platformApi.js";
import type {
  PaginatedVariants,
  ProjectDocumentRevision,
  ProjectNormalizeReport,
  Variant,
} from "../platformTypes.js";

// Se mockea el cliente HTTP tipado en el límite de red: ningún test toca fetch.
vi.mock("../platformApi.js", () => ({
  listAllDocuments: vi.fn(),
  listVariants: vi.fn(),
  uploadDocument: vi.fn(),
  normalizeDocuments: vi.fn(),
}));

const api = vi.mocked(platformApi);

function makeRevision(overrides: Partial<ProjectDocumentRevision> = {}): ProjectDocumentRevision {
  return {
    source_document_revision_id: "srev_1",
    logical_document_id: "ldoc_1",
    source_relpath: "manuales/seguridad/proc.pdf",
    file_size: 1024,
    raw_registered: true,
    normalized_registered: false,
    review_state: "pending",
    processing_status: "registered",
    uploaded_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeVariant(overrides: Partial<Variant> = {}): Variant {
  return {
    rag_variant_id: "ragv_1",
    project_id: "proj_alpha",
    processing_profile_id: "proc-1",
    chunking_profile_id: "chunk-1",
    embedding_profile_id: "local-bge-m3-v1",
    semantic_recipe_fingerprint: "fp",
    state: "ready",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function paginateVariants(items: Variant[]): PaginatedVariants {
  return { items, page: 1, page_size: 25, total_items: items.length, total_pages: 1 };
}

function makeReport(overrides: Partial<ProjectNormalizeReport> = {}): ProjectNormalizeReport {
  return {
    rag_variant_id: "ragv_1",
    processed: 1,
    needs_review: 0,
    skipped: 0,
    failed: 0,
    revision_ids: ["srev_1"],
    ...overrides,
  };
}

function selectProjectInStorage(projectId: string): void {
  writePlatformPreferences({ ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId: projectId });
}

beforeEach(() => {
  window.localStorage.clear();
  api.listAllDocuments.mockResolvedValue([]);
  api.listVariants.mockResolvedValue(paginateVariants([]));
  api.uploadDocument.mockResolvedValue(makeRevision({ source_document_revision_id: "srev_new" }));
  api.normalizeDocuments.mockResolvedValue(makeReport());
});

describe("DocumentIntakeWorkspace", () => {
  it("sube un documento enviando file + source_relpath", async () => {
    selectProjectInStorage("proj_alpha");

    const user = userEvent.setup();
    render(<DocumentIntakeWorkspace />);

    await screen.findByRole("heading", { name: "Intake documental" });

    const file = new File(["contenido"], "proc.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Archivo"), file);
    await user.type(
      screen.getByLabelText("Ruta lógica (source_relpath)"),
      "manuales/seguridad/proc.pdf",
    );
    await user.click(screen.getByRole("button", { name: /Subir documento/ }));

    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalledTimes(1));
    expect(api.uploadDocument).toHaveBeenCalledWith(
      "proj_alpha",
      file,
      "manuales/seguridad/proc.pdf",
    );
    // El srev_ resultante se muestra al operador.
    expect(await screen.findByText("srev_new")).toBeTruthy();
  });

  it("renderiza estados raw/normalized/review y los IDs canónicos", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([
      makeRevision({
        source_document_revision_id: "srev_1",
        logical_document_id: "ldoc_1",
        raw_registered: true,
        normalized_registered: true,
        review_state: "needs_review",
        processing_status: "normalized",
      }),
    ]);

    render(<DocumentIntakeWorkspace />);

    // IDs canónicos visibles.
    expect(await screen.findByText("srev_1")).toBeTruthy();
    expect(screen.getByText("ldoc_1")).toBeTruthy();
    // Estados en texto (no solo color).
    const table = screen.getByRole("table", { name: "Revisiones de documentos del proyecto" });
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).getByText("Normalizado")).toBeTruthy();
    expect(screen.getByText("needs_review")).toBeTruthy();
    expect(screen.getByText("normalized")).toBeTruthy();
  });

  it("selecciona todas las revisiones cargadas con un solo control", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([
      makeRevision({ source_document_revision_id: "srev_1" }),
      makeRevision({ source_document_revision_id: "srev_2", logical_document_id: "ldoc_2" }),
    ]);

    const user = userEvent.setup();
    render(<DocumentIntakeWorkspace />);

    await user.click(await screen.findByRole("button", { name: "Seleccionar todos" }));

    expect(screen.getByText("2 de 2 seleccionadas")).toBeTruthy();
    const checkboxes = screen.getAllByRole("checkbox", { name: /Seleccionar revisión/ });
    expect(checkboxes.every((box) => (box as HTMLInputElement).checked)).toBe(true);
  });

  it("normaliza enviando { rag_variant_id, document_revision_ids } sin processing_profile_id", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);
    api.listVariants.mockResolvedValue(paginateVariants([makeVariant()]));

    const user = userEvent.setup();
    render(<DocumentIntakeWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Seleccionar revisión srev_1/ }),
    );
    await user.selectOptions(screen.getByLabelText("Variante (rag_variant_id)"), "ragv_1");
    await user.click(screen.getByRole("button", { name: /Normalizar/ }));

    await waitFor(() => expect(api.normalizeDocuments).toHaveBeenCalledTimes(1));
    const body = api.normalizeDocuments.mock.calls[0][1];
    expect(body.rag_variant_id).toBe("ragv_1");
    expect(body.document_revision_ids).toEqual(["srev_1"]);
    // INVARIANTE D8: nunca se envía processing_profile_id libre.
    expect(Object.keys(body).sort()).toEqual(["document_revision_ids", "force", "rag_variant_id"]);
    expect("processing_profile_id" in body).toBe(false);
  });

  it("sin proyecto muestra estado vacío direccional y no llama a la API", async () => {
    render(<DocumentIntakeWorkspace />);

    expect(
      await screen.findByText(/Selecciona un proyecto para ver sus documentos/),
    ).toBeTruthy();
    expect(api.listAllDocuments).not.toHaveBeenCalled();
    expect(api.listVariants).not.toHaveBeenCalled();
  });

  it("ante 409 cross-project surfacea un mensaje fail-closed", async () => {
    selectProjectInStorage("proj_alpha");
    api.listAllDocuments.mockResolvedValue([makeRevision()]);
    api.listVariants.mockResolvedValue(paginateVariants([makeVariant()]));
    api.normalizeDocuments.mockRejectedValue({
      status: 409,
      code: "REVISION_PROJECT_MISMATCH",
    });

    const user = userEvent.setup();
    render(<DocumentIntakeWorkspace />);

    await user.click(
      await screen.findByRole("checkbox", { name: /Seleccionar revisión srev_1/ }),
    );
    await user.selectOptions(screen.getByLabelText("Variante (rag_variant_id)"), "ragv_1");
    await user.click(screen.getByRole("button", { name: /Normalizar/ }));

    expect(await screen.findByText(/pertenece a otro proyecto/)).toBeTruthy();
  });
});
