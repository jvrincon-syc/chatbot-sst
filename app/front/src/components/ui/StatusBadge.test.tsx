import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge.js";

describe("StatusBadge", () => {
  it("renderiza el label con el tono como clase (texto además de color)", () => {
    render(<StatusBadge label="needs_review" tone="warning" />);
    const badge = screen.getByText("needs_review");
    expect(badge.className).toContain("ui-status-chip");
    expect(badge.className).toContain("warning");
  });
});
