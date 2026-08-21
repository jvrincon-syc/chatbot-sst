import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PlatformWorkspace } from "./PlatformWorkspace.js";
import * as platformApi from "./platformApi.js";
import type {
  PaginatedProjects,
  ProjectConfiguration,
} from "./platformTypes.js";

// La sub-nav compone workspaces hermanos; se mockea el cliente HTTP para que el
// test verifique el switch de vistas sin tocar la red.
vi.mock("./platformApi.js", () => ({
  listProjects: vi.fn(),
  getConfiguration: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  updateConfiguration: vi.fn(),
  getVariantMatrix: vi.fn(),
  listAllVariants: vi.fn(),
  createVariant: vi.fn(),
  listAllDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  normalizeDocuments: vi.fn(),
  listAllCorpusSnapshots: vi.fn(),
  createCorpusSnapshot: vi.fn(),
  listAllReleases: vi.fn(),
  getRelease: vi.fn(),
  createReleaseDraft: vi.fn(),
  buildRelease: vi.fn(),
  validateRelease: vi.fn(),
  publishRelease: vi.fn(),
  retireRelease: vi.fn(),
}));

const api = vi.mocked(platformApi);

const emptyProjects: PaginatedProjects = {
  items: [],
  page: 1,
  page_size: 25,
  total_items: 0,
  total_pages: 1,
};
const emptyConfiguration: ProjectConfiguration = {
  corpus_organization_policy: "source-folders-v1",
  created_at: "2026-01-01T00:00:00Z",
  document_types: [],
  embedding_profiles: [],
  target_bindings: [],
  version: 1,
};

beforeEach(() => {
  window.localStorage.clear();
  api.listProjects.mockResolvedValue(emptyProjects);
  api.getVariantMatrix.mockResolvedValue([]);
  api.listAllVariants.mockResolvedValue([]);
  api.listAllDocuments.mockResolvedValue([]);
  api.listAllCorpusSnapshots.mockResolvedValue([]);
  api.listAllReleases.mockResolvedValue([]);
  api.getConfiguration.mockResolvedValue(emptyConfiguration);
});

describe("PlatformWorkspace", () => {
  it("cada botón de la sub-nav renderiza su workspace", async () => {
    const user = userEvent.setup();
    render(<PlatformWorkspace />);

    // Projects es la vista por defecto.
    expect(await screen.findByRole("heading", { name: "RAG Platform" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Variants" }));
    expect(await screen.findByRole("heading", { name: "Matriz de variantes" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "RAG Platform" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Documents" }));
    expect(await screen.findByRole("heading", { name: "Intake documental" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Matriz de variantes" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Corpus" }));
    expect(await screen.findByRole("heading", { name: "Snapshots de corpus" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Intake documental" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Releases" }));
    expect(
      await screen.findByRole("heading", { name: "Ciclo de vida de releases" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Snapshots de corpus" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByRole("heading", { name: "RAG Platform" })).toBeTruthy();
  });
});
