import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbeddingCatalogPanel } from "./EmbeddingCatalogPanel.js";
import type { EmbeddingProfile } from "../embeddingTypes.js";

function profile(overrides: Partial<EmbeddingProfile> = {}): EmbeddingProfile {
  return {
    profileId: "local-bge-m3-v1",
    provider: "bge",
    model: "BAAI/bge-m3",
    modelRevision: "5617a9f61b028005a4858fdac845db406aefb181",
    dimension: 1024,
    normalization: "l2",
    distanceMetric: "cosine",
    configurationFingerprint: null,
    ingestionOrigin: "local",
    chunkingVersion: "v1",
    vectorTable: "idx_vec_local_bge_m3_v1",
    defaultIndexingTargetId: "target-local",
    active: true,
    documentEnabled: false,
    queryEnabled: false,
    compatibilityStatus: "compatibility_not_proven",
    deprecatedAt: null,
    canEmbedDocuments: false,
    canEmbedQueries: false,
    ...overrides,
  };
}

const VERIFIED = profile({
  documentEnabled: true,
  queryEnabled: true,
  compatibilityStatus: "verified",
  canEmbedDocuments: true,
  canEmbedQueries: true,
});

function renderPanel(profiles: EmbeddingProfile[], onSelectProfile = vi.fn()) {
  render(
    <EmbeddingCatalogPanel
      profiles={profiles}
      loading={false}
      error={null}
      selectedProfileId={null}
      onSelectProfile={onSelectProfile}
    />,
  );
  return onSelectProfile;
}

describe("EmbeddingCatalogPanel", () => {
  it("states the fail-closed catalog block with its machine reason, not as an error", () => {
    renderPanel([profile(), profile({ profileId: "local-voyage-4-v1", provider: "voyage" })]);

    const banner = screen.getByRole("status", { name: "Catalogo de embedding bloqueado" });
    expect(banner.textContent).toContain(
      "Ningun perfil habilitado para embedding de documentos",
    );
    // The reason must be readable text, never color alone.
    expect(banner.textContent).toContain("compatibility_not_proven");
    // A correct fail-closed backend answer is not a frontend error.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("disables blocked options instead of hiding them", () => {
    renderPanel([profile()]);

    const option = screen.getByRole("option", { name: /local-bge-m3-v1/ });
    expect((option as HTMLOptionElement).disabled).toBe(true);
    expect(option.textContent).toContain("compatibility_not_proven");
  });

  it("drops the block and allows selection once a profile is verified", async () => {
    const onSelectProfile = renderPanel([VERIFIED, profile({ profileId: "local-voyage-4-v1" })]);

    expect(screen.queryByRole("status", { name: "Catalogo de embedding bloqueado" })).toBeNull();

    const select = screen.getByRole("combobox", { name: "Perfil de embedding" });
    await userEvent.selectOptions(select, "local-bge-m3-v1");

    expect(onSelectProfile).toHaveBeenCalledWith("local-bge-m3-v1");
  });
});
