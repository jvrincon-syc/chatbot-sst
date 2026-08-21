import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VariantMatrixWorkspace } from "./VariantMatrixWorkspace.js";
import { writePlatformPreferences } from "../platformPersistence.js";
import { DEFAULT_PLATFORM_PREFERENCES } from "../platformState.js";
import * as platformApi from "../platformApi.js";
import type { PaginatedVariants, Variant, VariantMatrixCell } from "../platformTypes.js";

// Se mockea el cliente HTTP tipado en el límite de red: ningún test toca fetch.
vi.mock("../platformApi.js", () => ({
  getVariantMatrix: vi.fn(),
  listVariants: vi.fn(),
  createVariant: vi.fn(),
}));

const api = vi.mocked(platformApi);

function makeCell(overrides: Partial<VariantMatrixCell> = {}): VariantMatrixCell {
  return {
    cell_id: "cell_a",
    buildable: true,
    blocked_reason: null,
    configuration_version: 3,
    target_binding_key: "primary",
    processing_profile_id: "proc-1",
    chunking_profile_id: "chunk-1",
    embedding_profile_id: "local-bge-m3-v1",
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
    state: "draft",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function paginate(items: Variant[]): PaginatedVariants {
  return { items, page: 1, page_size: 25, total_items: items.length, total_pages: 1 };
}

function selectProjectInStorage(projectId: string): void {
  writePlatformPreferences({ ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId: projectId });
}

beforeEach(() => {
  window.localStorage.clear();
  api.getVariantMatrix.mockResolvedValue([]);
  api.listVariants.mockResolvedValue(paginate([]));
  api.createVariant.mockResolvedValue(makeVariant());
});

describe("VariantMatrixWorkspace", () => {
  it("renderiza celdas construibles y bloqueadas; la bloqueada muestra su razón y no es seleccionable", async () => {
    selectProjectInStorage("proj_alpha");
    api.getVariantMatrix.mockResolvedValue([
      makeCell(),
      makeCell({
        cell_id: "cell_b",
        buildable: false,
        blocked_reason: "Falta perfil de embedding habilitado",
        target_binding_key: "secondary",
      }),
    ]);

    render(<VariantMatrixWorkspace />);

    // La construible es un botón seleccionable; la bloqueada no tiene botón.
    expect(await screen.findByRole("button", { name: /Seleccionar celda primary/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Seleccionar celda secondary/ })).toBeNull();

    // El motivo del bloqueo se comunica en texto, no solo por color.
    expect(screen.getByText(/Falta perfil de embedding habilitado/)).toBeTruthy();

    // Sin celda seleccionada, crear variante está deshabilitado con motivo visible.
    expect((screen.getByRole("button", { name: /Crear variante/ }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(
      screen.getByText(/Selecciona una celda construible de la matriz/),
    ).toBeTruthy();
  });

  it("crea una variante enviando exactamente { cell_id, variant_slug }", async () => {
    selectProjectInStorage("proj_alpha");
    api.getVariantMatrix.mockResolvedValue([makeCell()]);
    api.createVariant.mockResolvedValue(makeVariant({ rag_variant_id: "ragv_new" }));

    const user = userEvent.setup();
    render(<VariantMatrixWorkspace />);

    await user.click(await screen.findByRole("button", { name: /Seleccionar celda primary/ }));
    await user.type(screen.getByLabelText("Slug de la variante"), "mi-variante");
    await user.click(screen.getByRole("button", { name: /Crear variante/ }));

    await waitFor(() => expect(api.createVariant).toHaveBeenCalledTimes(1));
    expect(api.createVariant).toHaveBeenCalledWith("proj_alpha", {
      cell_id: "cell_a",
      variant_slug: "mi-variante",
    });
    // INVARIANTE Fase 7: el body no lleva IDs de perfil ni target físico.
    const body = api.createVariant.mock.calls[0][1];
    expect(Object.keys(body).sort()).toEqual(["cell_id", "variant_slug"]);
  });

  it("ante 409 STALE_VARIANT_MATRIX_CELL avisa, deselecciona la celda y refetch de la matriz", async () => {
    selectProjectInStorage("proj_alpha");
    api.getVariantMatrix.mockResolvedValue([makeCell()]);
    api.createVariant.mockRejectedValue({ status: 409, code: "STALE_VARIANT_MATRIX_CELL" });

    const user = userEvent.setup();
    render(<VariantMatrixWorkspace />);

    const cellButton = await screen.findByRole("button", { name: /Seleccionar celda primary/ });
    await user.click(cellButton);
    expect(cellButton.getAttribute("aria-pressed")).toBe("true");

    await user.type(screen.getByLabelText("Slug de la variante"), "mi-variante");
    const matrixCallsBefore = api.getVariantMatrix.mock.calls.length;
    await user.click(screen.getByRole("button", { name: /Crear variante/ }));

    // Notice de conflicto, celda deseleccionada y matriz re-consultada.
    expect(await screen.findByText(/quedó obsoleta/)).toBeTruthy();
    await waitFor(() =>
      expect(api.getVariantMatrix.mock.calls.length).toBeGreaterThan(matrixCallsBefore),
    );
    expect(
      screen
        .getByRole("button", { name: /Seleccionar celda primary/ })
        .getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("sin proyecto seleccionado muestra un estado vacío direccional", async () => {
    render(<VariantMatrixWorkspace />);

    expect(
      await screen.findByText(/Selecciona un proyecto para ver su matriz de recetas/),
    ).toBeTruthy();
    // Sin proyecto no se consulta la matriz.
    expect(api.getVariantMatrix).not.toHaveBeenCalled();
  });
});
