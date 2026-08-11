import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RetrievalSearchPanel } from "./RetrievalSearchPanel.js";
import type { RetrievalProfileStatus, RetrievalSearchResult } from "../retrievalTypes.js";

function buildStatus(): RetrievalProfileStatus {
  return {
    profile: {
      retrievalProfileId: "retrieval-1",
      consumerScopeType: "chatbot",
      consumerScopeId: "sst-default",
      corpusVersion: "phase1-main",
      embeddingProfileId: "local-bge-m3-v1",
      indexingTargetId: "target-1",
      lexicalFallbackPolicy: "allowed_when_vector_unavailable",
      active: true,
      validationStatus: "passed",
      validatedAt: null,
      lastRuntimeStatus: "ok",
      createdAt: null,
      deprecatedAt: null,
    },
    runtime: {
      retrievalProfileId: "retrieval-1",
      embeddingProfileId: "local-bge-m3-v1",
      indexingTargetId: "target-1",
      queryEngineAvailable: true,
      engineRevisionObserved: "rev-1",
      vectorRetrievalEnabled: true,
      lexicalFallbackAllowed: true,
      blockedReason: null,
    },
    readiness: {
      retrievalProfileId: "retrieval-1",
      ready: true,
      activeVectorRows: 10,
      activeDocumentCount: 3,
      embeddingBundleId: "bundle-1",
      blockingReasons: [],
    },
  };
}

function buildSearchResult(): RetrievalSearchResult {
  return {
    retrievalProfileId: "retrieval-1",
    topK: 1,
    items: [
      {
        nodeId: "child-1",
        documentId: "doc-1",
        parentNodeId: "parent-1",
        childChunkId: "child-1",
        text: "Texto del fragmento recuperado",
        score: 0.91,
        source: "vector",
        pageStart: 5,
        pageEnd: 5,
        sectionTitle: null,
        sectionPath: null,
        metadata: {},
        embeddingProfileId: "local-bge-m3-v1",
        corpusVersion: "phase1-main",
        embeddingBundleId: "bundle-1",
      },
      {
        nodeId: "parent-1",
        documentId: "doc-1",
        parentNodeId: null,
        childChunkId: "parent-1",
        text: "Texto del contexto expandido",
        score: 0.91,
        source: "vector",
        pageStart: 5,
        pageEnd: 6,
        sectionTitle: null,
        sectionPath: null,
        metadata: {},
        embeddingProfileId: "local-bge-m3-v1",
        corpusVersion: "phase1-main",
        embeddingBundleId: null,
      },
    ],
  };
}

describe("RetrievalSearchPanel", () => {
  it("renders evidence without exposing internal ids as visible headings", () => {
    render(
      <RetrievalSearchPanel
        retrievalProfileId="retrieval-1"
        status={buildStatus()}
        query="funciones del comite"
        onQueryChange={vi.fn()}
        topK={5}
        onTopKChange={vi.fn()}
        searchBusy={false}
        searchError={null}
        searchResult={buildSearchResult()}
        onSearch={vi.fn()}
      />,
    );

    expect(screen.getByText(/1 coincidencias base y 1 contextos ampliados/)).toBeTruthy();
    expect(screen.getByText("Fragmento sin seccion")).toBeTruthy();
    expect(screen.getByText("Contexto ampliado")).toBeTruthy();
    expect(screen.queryByText("child-1")).toBeNull();
    expect(screen.queryByText("parent-1")).toBeNull();
  });

  it("warns when the active retrieval scope only has one indexed document", () => {
    render(
      <RetrievalSearchPanel
        retrievalProfileId="retrieval-1"
        status={{
          ...buildStatus(),
          readiness: {
            ...buildStatus().readiness,
            activeDocumentCount: 1,
          },
        }}
        query="politica de desconexion"
        onQueryChange={vi.fn()}
        topK={5}
        onTopKChange={vi.fn()}
        searchBusy={false}
        searchError={null}
        searchResult={null}
        onSearch={vi.fn()}
      />,
    );

    expect(screen.getByText(/solo tiene 1 documento indexado/)).toBeTruthy();
  });
});
