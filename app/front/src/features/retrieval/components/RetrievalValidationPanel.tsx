import { AlertCircle, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import {
  retrievalCanValidate,
  retrievalValidationStatusLabel,
  retrievalValidationStatusTone,
} from "../retrievalState.js";
import type {
  RetrievalProfileStatus,
  RetrievalValidationResult,
} from "../retrievalTypes.js";

type RetrievalValidationPanelProps = {
  status: RetrievalProfileStatus | null;
  validationBusy: boolean;
  validationError: string | null;
  validationResult: RetrievalValidationResult | null;
  onValidate: () => void;
};

// Validation is an operator action independent from activation. It runs an
// internal synthetic query on the backend; no real user question is involved.
// It gates on runtime availability, not readiness.
export function RetrievalValidationPanel({
  status,
  validationBusy,
  validationError,
  validationResult,
  onValidate,
}: RetrievalValidationPanelProps) {
  const canValidate = status !== null && retrievalCanValidate(status);
  const blockedReason = !status
    ? "El perfil de retrieval aun no esta disponible."
    : !status.runtime.queryEngineAvailable
      ? "El motor de consultas no esta disponible."
      : null;

  return (
    <section className="panel" aria-label="Validacion de retrieval">
      <div className="panel-heading">
        <div>
          <h2>Validacion de retrieval</h2>
          <span>Usa una query sintetica interna; nunca una pregunta real de usuario.</span>
        </div>
        <span className="ui-pill">
          <ShieldCheck size={13} aria-hidden="true" /> Operador
        </span>
      </div>

      <div className="ui-panel-body">
        <div className="ui-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onValidate}
            disabled={!canValidate || validationBusy}
            title={blockedReason ?? "Validar el perfil de retrieval"}
          >
            {validationBusy ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
            Validar perfil
          </button>
          {blockedReason ? (
            <span className="pipeline-action-alert" role="status">
              <AlertCircle size={14} aria-hidden="true" />
              {blockedReason}
            </span>
          ) : null}
        </div>

        {validationError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{validationError}</span>
          </div>
        ) : null}

        {validationResult ? (
          <div className="ui-panel-body" aria-label="Resultado de validacion">
            <div className="ui-status-row">
              <span
                className={`ui-status-chip ${retrievalValidationStatusTone(
                  validationResult.status,
                )}`}
              >
                {validationResult.status === "passed" ? (
                  <CheckCircle2 size={13} aria-hidden="true" />
                ) : (
                  <AlertCircle size={13} aria-hidden="true" />
                )}{" "}
                {retrievalValidationStatusLabel(validationResult.status)}
              </span>
              <span className="ui-meta">
                {validationResult.candidatesFound} candidatos
              </span>
              {validationResult.queryDimension !== null ? (
                <span className="ui-meta">dim {validationResult.queryDimension}</span>
              ) : null}
              <span className="ui-meta">{validationResult.validatorVersion}</span>
            </div>

            {validationResult.blockingReasons.length > 0 ? (
              <div className="ui-warning" role="status">
                <strong>Motivos de bloqueo</strong>
                <ul>
                  {validationResult.blockingReasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
