import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OperatorApp } from "./OperatorApp.js";
import {
  DASHBOARD_VIEWS,
  isDashboardView,
} from "../dashboard/dashboardNavigation.js";
import type { StatusPayload } from "../dashboard/dashboardTypes.js";

const STATUS: StatusPayload = {
  summary: {
    total: 0,
    processed: 0,
    needsReview: 0,
    normalizedNeedsReview: 0,
    failed: 0,
    approved: 0,
    rejected: 0,
    runId: null,
    generatedAt: null,
    schemaVersion: "2.0",
  },
  llamaFirst: { provider: "local", configurationStatus: "ok" },
  settings: { ocrReviewThreshold: 0.8, ocrReviewThresholdPercent: 80 },
  documents: [],
  needsReview: [],
  errors: [],
  validation: null,
  manifests: {},
};

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(STATUS),
    })) as unknown as typeof fetch,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("operator navigation contract", () => {
  it("keeps the five legacy dashboard views untouched", () => {
    expect(DASHBOARD_VIEWS.map((item) => item.view)).toEqual([
      "operations",
      "review",
      "inventory",
      "chunking",
      "embedding-indexing",
    ]);
    expect(DASHBOARD_VIEWS).toHaveLength(5);
  });

  it("never treats platform as a dashboard view", () => {
    expect(isDashboardView("platform")).toBe(false);
  });
});

describe("OperatorApp", () => {
  it("labels the legacy surface in the rail", () => {
    stubFetch();
    render(<OperatorApp />);
    expect(screen.getByRole("button", { name: "Legacy pipeline" })).toBeTruthy();
  });

  it("switches between Platform and Legacy surfaces", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<OperatorApp />);

    // Platform is the default surface.
    expect(screen.getByRole("heading", { name: "RAG Platform" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Legacy pipeline" }));
    expect(screen.queryByRole("heading", { name: "RAG Platform" })).toBeNull();
    expect(screen.getByText("SST Pipeline")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Platform" }));
    expect(screen.getByRole("heading", { name: "RAG Platform" })).toBeTruthy();
    expect(screen.queryByText("SST Pipeline")).toBeNull();
  });
});
