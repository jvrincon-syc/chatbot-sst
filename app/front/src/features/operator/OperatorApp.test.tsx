import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { OperatorApp } from "./OperatorApp.js";
import {
  DASHBOARD_VIEWS,
  isDashboardView,
} from "../dashboard/dashboardNavigation.js";
import * as authApi from "./operatorAuthApi.js";

vi.mock("../dashboard/DashboardApp.js", () => ({
  DashboardApp: () => <div>SST Pipeline</div>,
}));

vi.mock("../platform/PlatformWorkspace.js", () => ({
  PlatformWorkspace: () => <h1>RAG Platform</h1>,
}));

vi.mock("./operatorAuthApi.js", () => ({
  getOperatorSession: vi.fn(),
  loginOperatorSession: vi.fn(),
  registerOperatorSession: vi.fn(),
  logoutOperatorSession: vi.fn(),
}));

const api = vi.mocked(authApi);

function authRequiredError() {
  return {
    status: 401,
    code: "HTTP_AUTH_REQUIRED",
    message: "Se requiere una sesión GUI válida.",
  };
}

function authNotConfiguredError() {
  return {
    status: 503,
    code: "HTTP_AUTH_NOT_CONFIGURED",
    message: "Problema de configuración del servidor de auth, no de tu sesión.",
  };
}

beforeEach(() => {
  api.getOperatorSession.mockResolvedValue({
    authenticated: true,
    principal_id: "op-1",
    project_scope: null,
  });
  api.loginOperatorSession.mockResolvedValue({
    authenticated: true,
    principal_id: "op-1",
    project_scope: null,
  });
  api.registerOperatorSession.mockResolvedValue({
    authenticated: true,
    principal_id: "nuevo-operador",
    project_scope: null,
  });
  api.logoutOperatorSession.mockResolvedValue({ authenticated: false });
});

afterEach(() => {
  vi.clearAllMocks();
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

describe("OperatorApp auth gate", () => {
  it("shows the login screen when the session probe returns 401", async () => {
    api.getOperatorSession.mockRejectedValueOnce(authRequiredError());

    render(<OperatorApp />);

    expect(await screen.findByRole("heading", { name: "Consola de operador" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Crear cuenta" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "RAG Platform" })).toBeNull();
  });

  it("opens the platform after submitting username and password", async () => {
    api.getOperatorSession.mockRejectedValueOnce(authRequiredError());
    const user = userEvent.setup();

    render(<OperatorApp />);

    await screen.findByRole("heading", { name: "Consola de operador" });
    await user.type(screen.getByLabelText("Usuario"), "op-1");
    await user.type(screen.getByLabelText("Contraseña"), "Clave123!");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(api.loginOperatorSession).toHaveBeenCalledWith({
      username: "op-1",
      password: "Clave123!",
    });
    expect(await screen.findByRole("heading", { name: "RAG Platform" })).toBeTruthy();
    expect(screen.getByText("op-1")).toBeTruthy();
  });

  it("shows a server configuration state for 503 auth-not-configured", async () => {
    api.getOperatorSession.mockRejectedValueOnce(authNotConfiguredError());

    render(<OperatorApp />);

    expect(
      await screen.findByText("Problema de configuración del servidor de auth, no de tu sesión."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /Reintentar/ })).toBeTruthy();
    expect(screen.queryByLabelText("Contraseña")).toBeNull();
  });

  it("creates a local user from the register form", async () => {
    api.getOperatorSession.mockRejectedValueOnce(authRequiredError());
    const user = userEvent.setup();

    render(<OperatorApp />);

    await user.click(await screen.findByRole("button", { name: "Crear cuenta" }));
    await user.type(screen.getByLabelText("Usuario"), "nuevo-operador");
    await user.type(screen.getByLabelText("Contraseña"), "Clave123!");
    await user.type(screen.getByLabelText("Confirmar contraseña"), "Clave123!");
    await user.click(screen.getByRole("button", { name: "Registrarme" }));

    expect(api.registerOperatorSession).toHaveBeenCalledWith({
      username: "nuevo-operador",
      password: "Clave123!",
    });
    expect(await screen.findByRole("heading", { name: "RAG Platform" })).toBeTruthy();
    expect(screen.getByText("nuevo-operador")).toBeTruthy();
  });

  it("registers with an optional project scope and wires it to the request", async () => {
    api.getOperatorSession.mockRejectedValueOnce(authRequiredError());
    api.registerOperatorSession.mockResolvedValue({
      authenticated: true,
      principal_id: "op-scoped",
      project_scope: ["proj_alpha", "proj_beta"],
    });
    const user = userEvent.setup();

    render(<OperatorApp />);

    await user.click(await screen.findByRole("button", { name: "Crear cuenta" }));
    await user.type(screen.getByLabelText("Usuario"), "op-scoped");
    await user.type(screen.getByLabelText("Contraseña"), "Clave123!");
    await user.type(screen.getByLabelText("Confirmar contraseña"), "Clave123!");
    await user.type(screen.getByLabelText("Proyectos"), "proj_alpha, proj_beta");
    await user.click(screen.getByRole("button", { name: "Registrarme" }));

    expect(api.registerOperatorSession).toHaveBeenCalledWith({
      username: "op-scoped",
      password: "Clave123!",
      project_scope: ["proj_alpha", "proj_beta"],
    });
    // El scope real del operador se muestra en el rail tras entrar.
    expect(await screen.findByText("2 proyectos")).toBeTruthy();
  });
});

describe("OperatorApp", () => {
  it("labels the legacy surface in the rail", async () => {
    render(<OperatorApp />);
    expect(await screen.findByRole("button", { name: "Legacy pipeline" })).toBeTruthy();
  });

  it("switches between Platform and Legacy surfaces", async () => {
    const user = userEvent.setup();
    render(<OperatorApp />);

    expect(await screen.findByRole("heading", { name: "RAG Platform" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Legacy pipeline" }));
    expect(screen.queryByRole("heading", { name: "RAG Platform" })).toBeNull();
    expect(screen.getByText("SST Pipeline")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Platform" }));
    expect(screen.getByRole("heading", { name: "RAG Platform" })).toBeTruthy();
    expect(screen.queryByText("SST Pipeline")).toBeNull();
  });

  it("logs out back to the login screen", async () => {
    const user = userEvent.setup();
    render(<OperatorApp />);

    await screen.findByRole("heading", { name: "RAG Platform" });
    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(api.logoutOperatorSession).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: "Consola de operador" })).toBeTruthy();
  });
});
