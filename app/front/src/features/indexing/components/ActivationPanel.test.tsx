import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActivationPanel } from "./ActivationPanel.js";
import type { IndexingRun } from "../indexingTypes.js";

function run(overrides: Partial<IndexingRun> = {}): IndexingRun {
  return {
    runId: "run-1",
    profileId: "local-bge-m3-v1",
    status: "completed",
    embeddingBundleId: "bundle-1",
    embeddingProfileId: "local-bge-m3-v1",
    indexingTargetId: "target-local",
    corpusVersion: "corpus-1",
    idempotencyKey: "key-1",
    requestFingerprint: "fp-1",
    validationStatus: "passed",
    activationStatus: "pending",
    startedAt: null,
    completedAt: null,
    summary: { requestedDocuments: 2, committedDocuments: 2, interrupted: false },
    warnings: [],
    links: { self: "", documents: "", errors: "", retrievalReadiness: "" },
    ...overrides,
  };
}

function renderPanel(props: Partial<Parameters<typeof ActivationPanel>[0]> = {}) {
  const onActivate = vi.fn();
  render(
    <ActivationPanel
      run={run()}
      readiness={null}
      lexicalFallbackPolicy="allowed_when_vector_unavailable"
      onPolicyChange={vi.fn()}
      activationBusy={false}
      activationError={null}
      activationResult={null}
      onActivate={onActivate}
      {...props}
    />,
  );
  return onActivate;
}

describe("ActivationPanel", () => {
  it("activates with policy only; the consumer scope is never an operator input", async () => {
    const onActivate = renderPanel();

    expect(screen.queryByLabelText(/consumer/i)).toBeNull();
    expect(
      screen.getByText(/El consumer scope lo resuelve el servidor/),
    ).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /Activar/ }));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it("explains in text why activation is disabled for an unfinished run", () => {
    renderPanel({ run: run({ status: "running" }) });

    const button = screen.getByRole("button", { name: /Activar/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText("El run de indexing debe completarse antes de activar."),
    ).toBeTruthy();
  });

  it("hands off the retrieval profile returned by a completed activation", () => {
    renderPanel({
      activationResult: {
        runId: "run-1",
        embeddingBundleId: "bundle-1",
        indexingTargetId: "target-local",
        retrievalProfileId: "retrieval-1",
        activatedRows: 12,
      },
    });

    expect(screen.getByText("Retrieval profile: retrieval-1")).toBeTruthy();
  });
});
