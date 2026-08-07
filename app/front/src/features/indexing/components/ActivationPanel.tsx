import { AlertCircle, ArrowRight, CheckCircle2, Loader2, Waypoints } from "lucide-react";
import { activationStatusLabel, canActivateIndexingRun } from "../indexingState.js";
import type {
  ActivationResult,
  IndexingRetrievalReadiness,
  IndexingRun,
} from "../indexingTypes.js";

export const LEXICAL_FALLBACK_POLICY_OPTIONS: readonly {
  value: string;
  label: string;
}[] = [
  { value: "allowed_when_vector_unavailable", label: "Permitir cuando el vector no este disponible" },
  { value: "never", label: "Nunca" },
  { value: "always", label: "Siempre" },
];

type ActivationPanelProps = {
  run: IndexingRun | null;
  readiness: IndexingRetrievalReadiness | null;
  lexicalFallbackPolicy: string;
  onPolicyChange: (policy: string) => void;
  activationBusy: boolean;
  activationError: string | null;
  activationResult: ActivationResult | null;
  onActivate: () => void;
};

const POLICY_LABEL_ID = "activation-policy-label";

// Activation is its own operator stage, separate from the indexing run form. It
// only sends run_id + lexical_fallback_policy; the consumer scope is resolved
// server-side and must never appear here. On success it exposes the
// retrieval_profile_id that hands off to the retrieval stage.
export function ActivationPanel({
  run,
  readiness,
  lexicalFallbackPolicy,
  onPolicyChange,
  activationBusy,
  activationError,
  activationResult,
  onActivate,
}: ActivationPanelProps) {
  const activatable = run !== null && canActivateIndexingRun(run);
  const blockedReason = !run
    ? "Aun no hay un run de indexing completado."
    : run.status !== "completed"
      ? "El run de indexing debe completarse antes de activar."
      : run.activationStatus !== "pending"
        ? `La activacion ya esta en estado ${activationStatusLabel(run.activationStatus)}.`
        : null;
  const canActivate = activatable && !activationBusy;

  return (
    <section className="panel" aria-label="Activacion del bundle indexado">
      <div className="panel-heading">
        <div>
          <h2>Activacion</h2>
          <span>Paso explicito e independiente del indexing. Habilita el handoff a retrieval.</span>
        </div>
        <span className="ui-pill">
          <Waypoints size={13} aria-hidden="true" /> Etapa
        </span>
      </div>

      <div className="ui-panel-body">
        <label className="ui-field">
          <span id={POLICY_LABEL_ID}>Politica de fallback lexico</span>
          <select
            aria-labelledby={POLICY_LABEL_ID}
            value={lexicalFallbackPolicy}
            disabled={!activatable}
            onChange={(event) => onPolicyChange(event.currentTarget.value)}
          >
            {LEXICAL_FALLBACK_POLICY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span className="ui-field-note">
            El consumer scope lo resuelve el servidor; no se envia desde la interfaz.
          </span>
        </label>

        <div className="ui-actions">
          <button
            type="button"
            className="primary-button"
            onClick={onActivate}
            disabled={!canActivate}
            title={blockedReason ?? "Activar el bundle indexado"}
          >
            {activationBusy ? <Loader2 className="spin" size={16} /> : <ArrowRight size={16} />}
            Activar
          </button>
          {blockedReason ? (
            <span className="pipeline-action-alert" role="status">
              <AlertCircle size={14} aria-hidden="true" />
              {blockedReason}
            </span>
          ) : null}
        </div>

        {activationError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{activationError}</span>
          </div>
        ) : null}

        {readiness ? (
          <div
            className={readiness.ready ? "ui-note" : "ui-warning"}
            role="status"
          >
            <strong>
              Retrieval readiness: {readiness.ready ? "listo" : "bloqueado"} ·{" "}
              {readiness.activeVectorRows} filas activas
            </strong>
            {readiness.blockingReasons.length > 0 ? (
              <ul>
                {readiness.blockingReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {activationResult ? (
          <div className="ui-note" role="status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <div className="ui-row-cell">
              <strong>Activacion completada · {activationResult.activatedRows} filas</strong>
              <span>
                {activationResult.retrievalProfileId
                  ? `Retrieval profile: ${activationResult.retrievalProfileId}`
                  : "Sin retrieval profile devuelto"}
              </span>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
