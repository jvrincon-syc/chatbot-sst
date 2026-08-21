import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { StatePanel } from "./StatePanel.js";

describe("StatePanel", () => {
  it("el estado error expone el mensaje con role=alert y un retry opcional", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<StatePanel kind="error" message="No autorizado" onRetry={onRetry} />);

    expect(screen.getByRole("alert").textContent).toBe("No autorizado");
    await user.click(screen.getByRole("button", { name: /Reintentar/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("sin onRetry el estado error no muestra botón (bloqueo visible, sin acción falsa)", () => {
    render(<StatePanel kind="error" message="Prohibido" />);
    expect(screen.getByRole("alert").textContent).toBe("Prohibido");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("loading e info muestran el mensaje", () => {
    const { rerender } = render(<StatePanel kind="loading" message="Cargando..." />);
    expect(screen.getByText("Cargando...")).toBeTruthy();
    rerender(<StatePanel kind="info" message="Selecciona un proyecto" />);
    expect(screen.getByText("Selecciona un proyecto")).toBeTruthy();
  });
});
