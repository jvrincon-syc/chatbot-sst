import { useState } from "react";
import { Hammer, Loader2, Rocket, ShieldCheck, XOctagon } from "lucide-react";
import type { Release } from "../platformTypes.js";

// Máquina de estados EXACTA (ReleaseState): draft → validated → published → retired,
// con `failed` como terminal de fallo. El riel muestra el orden REAL (no decorativo)
// y solo se ofrecen las transiciones válidas para el estado actual. El backend es la
// autoridad: aquí nunca se muestra una acción que el estado no permite.
const RAIL: readonly string[] = ["draft", "validated", "published", "retired"];

type BusyAction = null | "build" | "validate" | "publish" | "retire";

export function ReleaseLifecycle({
  release,
  busyAction,
  onBuild,
  onValidate,
  onPublish,
  onRetire,
}: {
  release: Release | null;
  busyAction: BusyAction;
  onBuild: () => void;
  onValidate: () => void;
  onPublish: () => void;
  onRetire: (reason: string) => void;
}) {
  if (!release) {
    return (
      <div className="ui-empty">
        <ShieldCheck size={24} />
        <span>Selecciona o crea una release para ver su ciclo de vida.</span>
      </div>
    );
  }

  const state = release.state;
  const currentIndex = RAIL.indexOf(state);
  const isFailed = state === "failed";

  return (
    <div className="release-lifecycle">
      <ol className="release-rail" aria-label={`Estado de la release: ${state}`}>
        {RAIL.map((step, index) => {
          const status =
            currentIndex >= 0 && index < currentIndex
              ? "done"
              : index === currentIndex
                ? "current"
                : "pending";
          return (
            <li
              key={step}
              className={`release-step ${status}`}
              aria-current={status === "current" ? "step" : undefined}
            >
              <span className="release-step-dot" aria-hidden="true" />
              <span className="release-step-label">{step}</span>
              {status === "current" ? <span className="ui-hint">actual</span> : null}
            </li>
          );
        })}
      </ol>

      {isFailed ? (
        <p className="release-terminal" role="status">
          <XOctagon size={16} aria-hidden="true" />
          Esta release falló ({state}). Es un estado terminal: no admite más transiciones.
        </p>
      ) : null}

      <ReleaseActions
        state={state}
        busyAction={busyAction}
        onBuild={onBuild}
        onValidate={onValidate}
        onPublish={onPublish}
        onRetire={onRetire}
      />
    </div>
  );
}

function ReleaseActions({
  state,
  busyAction,
  onBuild,
  onValidate,
  onPublish,
  onRetire,
}: {
  state: string;
  busyAction: BusyAction;
  onBuild: () => void;
  onValidate: () => void;
  onPublish: () => void;
  onRetire: (reason: string) => void;
}) {
  const busy = busyAction !== null;

  if (state === "draft") {
    return (
      <div className="platform-actions">
        {/* Build no transiciona: la release sigue en draft y produce un informe. */}
        <button className="secondary-button" type="button" onClick={onBuild} disabled={busy}>
          {busyAction === "build" ? <Loader2 className="spin" size={16} /> : <Hammer size={16} />}
          Construir (build)
        </button>
        <button className="primary-button" type="button" onClick={onValidate} disabled={busy}>
          {busyAction === "validate" ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
          Validar
        </button>
      </div>
    );
  }

  if (state === "validated") {
    return (
      <div className="release-action-stack">
        <div className="platform-actions">
          <button className="primary-button" type="button" onClick={onPublish} disabled={busy}>
            {busyAction === "publish" ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <Rocket size={16} />
            )}
            Publicar
          </button>
        </div>
        <RetireControl busyAction={busyAction} onRetire={onRetire} />
      </div>
    );
  }

  if (state === "published") {
    return <RetireControl busyAction={busyAction} onRetire={onRetire} />;
  }

  // retired / failed / desconocido: estado terminal, sin acciones.
  return (
    <p className="ui-hint" role="note">
      Estado terminal: no hay más transiciones disponibles.
    </p>
  );
}

// Retirar es una acción de confirmación (§11 AGENTS_front): exige un motivo explícito
// antes de ejecutarse. No se expone la Idempotency-Key en la UI.
function RetireControl({
  busyAction,
  onRetire,
}: {
  busyAction: BusyAction;
  onRetire: (reason: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const busy = busyAction !== null;

  if (!open) {
    return (
      <div className="platform-actions">
        <button
          className="reject-button"
          type="button"
          onClick={() => setOpen(true)}
          disabled={busy}
        >
          <XOctagon size={16} />
          Retirar…
        </button>
      </div>
    );
  }

  return (
    <form
      className="release-retire-form"
      onSubmit={(event) => {
        event.preventDefault();
        onRetire(reason);
      }}
    >
      <div className="ui-field">
        <label htmlFor="release-retire-reason">Motivo del retiro (obligatorio)</label>
        <textarea
          id="release-retire-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={2}
          placeholder="Explica por qué se retira esta release."
        />
      </div>
      <div className="platform-actions">
        <button
          className="reject-button"
          type="submit"
          disabled={busy || reason.trim().length === 0}
          title={reason.trim().length === 0 ? "Escribe un motivo para retirar." : undefined}
        >
          {busyAction === "retire" ? <Loader2 className="spin" size={16} /> : <XOctagon size={16} />}
          Confirmar retiro
        </button>
        <button
          className="ghost-button"
          type="button"
          onClick={() => {
            setOpen(false);
            setReason("");
          }}
          disabled={busy}
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
