import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

// Estado no-feliz compartido (loading / empty / info / error) para los workspaces
// de plataforma: un solo bloque `.ui-empty` en vez de repetirlo en cada tabla.
// `error` expone el mensaje con role="alert" y un retry opcional; nunca oculta el
// bloqueo detrás de un genérico (fail-closed).
export type StatePanelKind = "loading" | "empty" | "info" | "error";

export function StatePanel({
  kind,
  message,
  icon,
  onRetry,
}: {
  kind: StatePanelKind;
  message: string;
  icon?: JSX.Element;
  onRetry?: () => void;
}) {
  if (kind === "loading") {
    return (
      <div className="ui-empty">
        <Loader2 className="spin" size={22} />
        <span>{message}</span>
      </div>
    );
  }

  if (kind === "error") {
    return (
      <div className="ui-empty">
        <AlertCircle size={24} />
        <span role="alert">{message}</span>
        {onRetry ? (
          <button className="secondary-button" type="button" onClick={onRetry}>
            <RefreshCw size={16} />
            Reintentar
          </button>
        ) : null}
      </div>
    );
  }

  // empty / info: icono opcional del dominio + copia direccional.
  return (
    <div className="ui-empty">
      {icon}
      <span>{message}</span>
    </div>
  );
}
