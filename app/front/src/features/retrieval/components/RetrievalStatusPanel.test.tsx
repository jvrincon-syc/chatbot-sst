import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RetrievalStatusPanel } from "./RetrievalStatusPanel.js";
import type { RetrievalProfileStatus } from "../retrievalTypes.js";

function status(overrides: Partial<RetrievalProfileStatus> = {}): RetrievalProfileStatus {
  return {
    profile: {
      retrievalProfileId: "retrieval-1",
      consumerScopeType: "tenant",
      consumerScopeId: "sst",
      corpusVersion: "corpus-1",
      embeddingProfileId: "local-bge-m3-v1",
      indexingTargetId: "target-local",
      lexicalFallbackPolicy: "allowed_when_vector_unavailable",
      active: true,
      validationStatus: "pending",
      validatedAt: null,
      lastRuntimeStatus: "never_run",
      createdAt: null,
      deprecatedAt: null,
    },
    runtime: {
      retrievalProfileId: "retrieval-1",
      embeddingProfileId: "local-bge-m3-v1",
      indexingTargetId: "target-local",
      queryEngineAvailable: true,
      engineRevisionObserved: "5617a9f",
      vectorRetrievalEnabled: true,
      lexicalFallbackAllowed: false,
      blockedReason: null,
    },
    readiness: {
      retrievalProfileId: "retrieval-1",
      ready: true,
      activeVectorRows: 42,
      activeDocumentCount: 7,
      embeddingBundleId: "bundle-1",
      blockingReasons: [],
    },
    ...overrides,
  };
}

describe("RetrievalStatusPanel", () => {
  it("stays unavailable until activation returns a retrieval profile", () => {
    render(
      <RetrievalStatusPanel retrievalProfileId={null} status={null} loading={false} error={null} />,
    );

    expect(screen.getByText(/Retrieval no esta disponible todavia/)).toBeTruthy();
  });

  it("keeps a healthy runtime visible while readiness is blocked", () => {
    render(
      <RetrievalStatusPanel
        retrievalProfileId="retrieval-1"
        status={status({
          readiness: {
            retrievalProfileId: "retrieval-1",
            ready: false,
            activeVectorRows: 0,
            activeDocumentCount: 0,
            embeddingBundleId: null,
            blockingReasons: ["no_active_vector_rows"],
          },
        })}
        loading={false}
        error={null}
      />,
    );

    const runtime = screen.getByLabelText("Runtime del motor de consultas");
    expect(runtime.textContent).toContain("Motor disponible");

    const readiness = screen.getByLabelText("Readiness de retrieval");
    expect(readiness.textContent).toContain("Bloqueado");
    expect(screen.getByText("no_active_vector_rows")).toBeTruthy();
  });

  it("makes a one-document active scope visible to the operator", () => {
    render(
      <RetrievalStatusPanel
        retrievalProfileId="retrieval-1"
        status={status({
          readiness: {
            retrievalProfileId: "retrieval-1",
            ready: true,
            activeVectorRows: 20,
            activeDocumentCount: 1,
            embeddingBundleId: "bundle-1",
            blockingReasons: [],
          },
        })}
        loading={false}
        error={null}
      />,
    );

    expect(screen.getByText("1 documento activo")).toBeTruthy();
    expect(screen.getByText(/solo cubre 1 documento indexado/)).toBeTruthy();
  });

  it("surfaces a transport error as an alert without faking a status", () => {
    render(
      <RetrievalStatusPanel
        retrievalProfileId="retrieval-1"
        status={null}
        loading={false}
        error="RETRIEVAL_STATUS_UNAVAILABLE"
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain("RETRIEVAL_STATUS_UNAVAILABLE");
    expect(screen.queryByLabelText("Readiness de retrieval")).toBeNull();
  });
});
