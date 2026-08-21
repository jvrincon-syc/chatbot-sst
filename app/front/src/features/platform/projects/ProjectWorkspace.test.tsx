import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ProjectWorkspace } from "./ProjectWorkspace.js";
import { writePlatformPreferences } from "../platformPersistence.js";
import { DEFAULT_PLATFORM_PREFERENCES } from "../platformState.js";
import * as platformApi from "../platformApi.js";
import type {
  PaginatedProjects,
  Project,
  ProjectConfiguration,
} from "../platformTypes.js";

// Se mockea el cliente HTTP tipado en el límite de red: ningún test toca fetch.
vi.mock("../platformApi.js", () => ({
  listProjects: vi.fn(),
  getConfiguration: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  updateConfiguration: vi.fn(),
}));

const api = vi.mocked(platformApi);

function makeConfig(overrides: Partial<ProjectConfiguration> = {}): ProjectConfiguration {
  return {
    version: 3,
    corpus_organization_policy: "source-folders-v1",
    document_types: [{ code: "policy", display_name: "Política", template: "sst" }],
    embedding_profiles: [{ embedding_profile_id: "local-bge-m3-v1", enabled: true }],
    target_bindings: [{ binding_key: "primary", embedding_profile_id: "local-bge-m3-v1" }],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: "proj_alpha",
    display_name: "Proyecto Alpha",
    state: "active",
    configuration: makeConfig(),
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function paginate(items: Project[]): PaginatedProjects {
  return { items, page: 1, page_size: 25, total_items: items.length, total_pages: 1 };
}

function selectProjectInStorage(projectId: string): void {
  writePlatformPreferences({ ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId: projectId });
}

beforeEach(() => {
  window.localStorage.clear();
  api.listProjects.mockResolvedValue(paginate([]));
  api.getConfiguration.mockResolvedValue(makeConfig());
  api.createProject.mockResolvedValue(makeProject());
  api.updateProject.mockResolvedValue(makeProject());
  api.updateConfiguration.mockResolvedValue(makeConfig());
});

describe("ProjectWorkspace", () => {
  it("renderiza proyectos y carga la configuración al seleccionar uno", async () => {
    const alpha = makeProject();
    const beta = makeProject({ project_id: "proj_beta", display_name: "Proyecto Beta" });
    api.listProjects.mockResolvedValue(paginate([alpha, beta]));
    api.getConfiguration.mockResolvedValue(makeConfig({ version: 7 }));

    const user = userEvent.setup();
    render(<ProjectWorkspace />);

    const betaButton = await screen.findByRole("button", { name: /Proyecto Beta/ });
    await user.click(betaButton);

    await waitFor(() =>
      expect(api.getConfiguration).toHaveBeenCalledWith("proj_beta", expect.anything()),
    );
    expect(await screen.findByText("Config v7")).toBeTruthy();
    expect(betaButton.getAttribute("aria-current")).toBe("true");
  });

  it("crea un proyecto con el body de contrato correcto", async () => {
    api.listProjects.mockResolvedValue(paginate([]));
    api.createProject.mockResolvedValue(
      makeProject({ project_id: "proj_new", display_name: "Nuevo" }),
    );

    const user = userEvent.setup();
    render(<ProjectWorkspace />);

    await user.click(await screen.findByRole("button", { name: /Nuevo proyecto/ }));
    await user.type(screen.getByLabelText("Slug"), "nuevo-proyecto");
    await user.type(screen.getByLabelText("Nombre visible"), "Nuevo");
    await user.selectOptions(
      screen.getByLabelText("Política de organización"),
      "document-types-v1",
    );
    await user.selectOptions(screen.getByLabelText("Plantilla de tipos"), "sst");
    await user.click(screen.getByRole("button", { name: /Crear proyecto/ }));

    await waitFor(() =>
      expect(api.createProject).toHaveBeenCalledWith({
        project_slug: "nuevo-proyecto",
        display_name: "Nuevo",
        corpus_organization_policy: "document-types-v1",
        document_type_template: "sst",
      }),
    );
  });

  it("no expone ningún input de target físico y muestra bindings solo lectura", async () => {
    api.listProjects.mockResolvedValue(paginate([makeProject()]));
    api.getConfiguration.mockResolvedValue(makeConfig());
    selectProjectInStorage("proj_alpha");

    render(<ProjectWorkspace />);

    const binding = await screen.findByText(/primary/);
    expect(binding.tagName).toBe("SPAN");
    expect(binding.textContent).toContain("local-bge-m3-v1");
    expect(screen.getByText(/target físico lo gestiona el servidor/i)).toBeTruthy();

    // El target físico nunca cruza la UI: no hay ningún control editable de target.
    expect(screen.queryByRole("textbox", { name: /target/i })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /target/i })).toBeNull();
  });

  it("muestra un notice de no autorizado cuando la configuración responde 403", async () => {
    api.listProjects.mockResolvedValue(paginate([makeProject()]));
    api.getConfiguration.mockRejectedValue({ status: 403, code: "FORBIDDEN" });
    selectProjectInStorage("proj_alpha");

    render(<ProjectWorkspace />);

    const surfaced = await screen.findAllByText("No autorizado para esta operación.");
    expect(surfaced.length).toBeGreaterThan(0);
  });

  it("surfacea el mensaje de validación 422 al guardar configuración", async () => {
    api.listProjects.mockResolvedValue(paginate([makeProject()]));
    api.getConfiguration.mockResolvedValue(makeConfig());
    api.updateConfiguration.mockRejectedValue({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "document_types.0.code: no puede estar vacío",
    });
    selectProjectInStorage("proj_alpha");

    const user = userEvent.setup();
    render(<ProjectWorkspace />);

    await user.click(await screen.findByRole("button", { name: /Guardar nueva versión/ }));

    expect(
      await screen.findByText("document_types.0.code: no puede estar vacío"),
    ).toBeTruthy();
  });

  it("guarda una nueva versión con política, tipos y perfiles de embedding", async () => {
    api.listProjects.mockResolvedValue(paginate([makeProject()]));
    api.getConfiguration.mockResolvedValue(makeConfig());
    api.updateConfiguration.mockResolvedValue(makeConfig({ version: 4 }));
    selectProjectInStorage("proj_alpha");

    const user = userEvent.setup();
    render(<ProjectWorkspace />);

    await user.selectOptions(
      await screen.findByLabelText("Política de organización del corpus"),
      "hybrid-v1",
    );
    await user.click(screen.getByRole("button", { name: /Guardar nueva versión/ }));

    await waitFor(() =>
      expect(api.updateConfiguration).toHaveBeenCalledWith("proj_alpha", {
        corpus_organization_policy: "hybrid-v1",
        document_types: [{ code: "policy", display_name: "Política", template: "sst" }],
        embedding_profiles: [{ embedding_profile_id: "local-bge-m3-v1", enabled: true }],
      }),
    );
  });
});
