import { useCallback, useEffect, useState } from "react";

import { mapPipelineError } from "../../shared/api/errorMapping.js";
import {
  getOperatorSession,
  loginOperatorSession,
  logoutOperatorSession,
  registerOperatorSession,
  type AuthenticatedOperatorSession,
  type OperatorCredentials,
  type OperatorRegistration,
} from "./operatorAuthApi.js";

export type OperatorSessionState =
  | { status: "checking" }
  | { status: "anonymous"; error: string | null; submitting: boolean }
  | { status: "misconfigured"; message: string }
  | { status: "error"; message: string }
  | {
      status: "authenticated";
      session: AuthenticatedOperatorSession;
      loggingOut: boolean;
    };

function isAuthNotConfigured(error: unknown): boolean {
  const mapped = mapPipelineError(error);
  return mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED";
}

function isMissingGuiSession(error: unknown): boolean {
  return mapPipelineError(error).status === 401;
}

function authMessage(error: unknown): string {
  return mapPipelineError(error).message;
}

function loginMessage(error: unknown): string {
  if (isAuthNotConfigured(error)) {
    return "Problema de configuración del servidor de auth, no de tu sesión.";
  }
  if (isMissingGuiSession(error)) {
    return "Usuario o contraseña inválidos.";
  }
  return authMessage(error);
}

function stateFromSessionProbeError(error: unknown): OperatorSessionState {
  if (isMissingGuiSession(error)) {
    return { status: "anonymous", error: null, submitting: false };
  }
  if (isAuthNotConfigured(error)) {
    return {
      status: "misconfigured",
      message: "Problema de configuración del servidor de auth, no de tu sesión.",
    };
  }
  return { status: "error", message: authMessage(error) };
}

export function useOperatorSession() {
  const [state, setState] = useState<OperatorSessionState>({ status: "checking" });

  const probeSession = useCallback(async (signal?: AbortSignal) => {
    setState({ status: "checking" });
    try {
      const session = await getOperatorSession({ signal });
      if (signal?.aborted) {
        return;
      }
      if (!session.authenticated) {
        setState({ status: "anonymous", error: null, submitting: false });
        return;
      }
      setState({
        status: "authenticated",
        session,
        loggingOut: false,
      });
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setState(stateFromSessionProbeError(error));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void probeSession(controller.signal);
    return () => controller.abort();
  }, [probeSession]);

  const login = useCallback(async (body: OperatorCredentials): Promise<boolean> => {
    setState({ status: "anonymous", error: null, submitting: true });
    try {
      const session = await loginOperatorSession(body);
      setState({
        status: "authenticated",
        session,
        loggingOut: false,
      });
      return true;
    } catch (error) {
      if (isAuthNotConfigured(error)) {
        setState({
          status: "misconfigured",
          message: "Problema de configuración del servidor de auth, no de tu sesión.",
        });
        return false;
      }
      setState({
        status: "anonymous",
        error: loginMessage(error),
        submitting: false,
      });
      return false;
    }
  }, []);

  const register = useCallback(
    async (body: OperatorRegistration): Promise<boolean> => {
      setState({ status: "anonymous", error: null, submitting: true });
      try {
        const session = await registerOperatorSession(body);
        setState({
          status: "authenticated",
          session,
          loggingOut: false,
        });
        return true;
      } catch (error) {
        if (isAuthNotConfigured(error)) {
          setState({
            status: "misconfigured",
            message: "Problema de configuración del servidor de auth, no de tu sesión.",
          });
          return false;
        }
        setState({
          status: "anonymous",
          error: authMessage(error),
          submitting: false,
        });
        return false;
      }
    },
    [],
  );

  const logout = useCallback(async (): Promise<void> => {
    setState((current) =>
      current.status === "authenticated"
        ? { ...current, loggingOut: true }
        : current,
    );
    try {
      await logoutOperatorSession();
      setState({ status: "anonymous", error: null, submitting: false });
    } catch (error) {
      if (isMissingGuiSession(error)) {
        setState({ status: "anonymous", error: null, submitting: false });
        return;
      }
      setState((current) =>
        current.status === "authenticated"
          ? { ...current, loggingOut: false }
          : { status: "error", message: authMessage(error) },
      );
    }
  }, []);

  return {
    state,
    login,
    register,
    logout,
    refresh: probeSession,
  };
}
