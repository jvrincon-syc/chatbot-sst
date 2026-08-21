import { Loader2, RefreshCw } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import type {
  OperatorCredentials,
  OperatorRegistration,
} from "../operatorAuthApi.js";
import type { OperatorSessionState } from "../useOperatorSession.js";

type AuthMode = "login" | "register";

// Convierte el campo libre de proyectos ("proj_a, proj_b") en la lista que espera
// el backend. Vacío = operador global (sin recorte); no se envía el campo.
function parseScope(raw: string): string[] | undefined {
  const ids = raw
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  return ids.length > 0 ? ids : undefined;
}

export function OperatorAuthWorkspace({
  state,
  onLogin,
  onRegister,
  onRetry,
}: {
  state: Exclude<OperatorSessionState, { status: "authenticated" }>;
  onLogin: (body: OperatorCredentials) => Promise<boolean>;
  onRegister: (body: OperatorRegistration) => Promise<boolean>;
  onRetry: () => void;
}) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [scope, setScope] = useState("");

  useEffect(() => {
    if (state.status !== "anonymous") {
      setMode("login");
      setUsername("");
      setPassword("");
      setConfirmPassword("");
      setScope("");
    }
  }, [state.status]);

  const isRegister = mode === "register";
  const submitting = state.status === "anonymous" && state.submitting;
  const passwordMismatch =
    isRegister && confirmPassword.length > 0 && password !== confirmPassword;
  const canSubmit =
    !submitting &&
    username.trim().length > 0 &&
    password.length > 0 &&
    !passwordMismatch;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    let ok: boolean;
    if (isRegister) {
      const registration: OperatorRegistration = { username: username.trim(), password };
      const scopeIds = parseScope(scope);
      // Solo se incluye el scope si el operador declaró proyectos; vacío = global.
      if (scopeIds) {
        registration.project_scope = scopeIds;
      }
      ok = await onRegister(registration);
    } else {
      ok = await onLogin({ username: username.trim(), password });
    }
    if (ok) {
      setUsername("");
      setPassword("");
      setConfirmPassword("");
      setScope("");
    }
  }

  return (
    <main className="operator-auth">
      <aside className="operator-auth-aside">
        <div className="operator-auth-aside-inner">
          <span className="operator-auth-wordmark">chatbot·sst</span>
          <p className="operator-auth-tagline">
            Consola interna para construir, comparar y publicar releases RAG por proyecto.
          </p>
          <span className="operator-auth-lineage">project → variant → release</span>
        </div>
      </aside>

      <section className="operator-auth-main" aria-label="Acceso de operador">
        <div className="operator-auth-form-wrap">
          <header className="operator-auth-brand">
            <h1>{isRegister ? "Nueva cuenta" : "Consola de operador"}</h1>
            <p>
              {isRegister
                ? "Crea tu acceso local a la plataforma RAG."
                : "Entra para administrar proyectos, variantes y releases."}
            </p>
          </header>

          {state.status === "checking" ? (
          <div className="ui-empty compact">
            <Loader2 className="spin" size={20} />
            <span>Comprobando sesión…</span>
          </div>
        ) : state.status === "misconfigured" || state.status === "error" ? (
          <div className="operator-auth-body">
            <DashboardNotice tone="danger" message={state.message} />
            <button className="ghost-button" type="button" onClick={onRetry}>
              <RefreshCw size={16} />
              Reintentar
            </button>
          </div>
        ) : (
          <form className="operator-auth-body" onSubmit={handleSubmit}>
            <div className="segmented-control operator-auth-modes" aria-label="Modo de acceso">
              <button
                type="button"
                aria-pressed={!isRegister}
                className={isRegister ? "" : "active"}
                onClick={() => setMode("login")}
              >
                Iniciar sesión
              </button>
              <button
                type="button"
                aria-pressed={isRegister}
                className={isRegister ? "active" : ""}
                onClick={() => setMode("register")}
              >
                Crear cuenta
              </button>
            </div>

            {state.error ? <DashboardNotice tone="danger" message={state.error} /> : null}

            <label className="ui-field" htmlFor="operator-username">
              Usuario
              <input
                id="operator-username"
                aria-label="Usuario"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.currentTarget.value)}
                placeholder="tu.usuario"
                spellCheck={false}
              />
            </label>

            <label className="ui-field" htmlFor="operator-password">
              Contraseña
              <input
                id="operator-password"
                aria-label="Contraseña"
                type="password"
                autoComplete={isRegister ? "new-password" : "current-password"}
                value={password}
                onChange={(event) => setPassword(event.currentTarget.value)}
                placeholder="••••••••"
              />
            </label>

            {isRegister ? (
              <>
                <label className="ui-field" htmlFor="operator-confirm">
                  Confirmar contraseña
                  <input
                    id="operator-confirm"
                    aria-label="Confirmar contraseña"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.currentTarget.value)}
                    placeholder="Repite la contraseña"
                  />
                  {passwordMismatch ? (
                    <span className="ui-field-note error">Las contraseñas no coinciden.</span>
                  ) : null}
                </label>

                <label className="ui-field" htmlFor="operator-scope">
                  Proyectos <span className="operator-auth-optional">(opcional)</span>
                  <input
                    id="operator-scope"
                    aria-label="Proyectos"
                    value={scope}
                    onChange={(event) => setScope(event.currentTarget.value)}
                    placeholder="proj_alpha, proj_beta"
                    spellCheck={false}
                  />
                  <span className="ui-field-note">
                    Vacío = acceso a todos los proyectos.
                  </span>
                </label>
              </>
            ) : null}

            <button className="primary-button operator-auth-submit" type="submit" disabled={!canSubmit}>
              {submitting ? <Loader2 className="spin" size={16} /> : null}
              {isRegister ? "Registrarme" : "Entrar"}
            </button>
          </form>
          )}
        </div>
      </section>
    </main>
  );
}
