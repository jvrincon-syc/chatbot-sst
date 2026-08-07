import { AlertCircle, Ban, CheckCircle2, Loader2, Search } from "lucide-react";
import {
  deriveRetrievalStageState,
  retrievalRuntimeStatusLabel,
  retrievalRuntimeStatusTone,
} from "../retrievalState.js";
import type { RetrievalProfileStatus } from "../retrievalTypes.js";

type RetrievalStatusPanelProps = {
  retrievalProfileId: string | null;
  status: RetrievalProfileStatus | null;
  loading: boolean;
  error: string | null;
};

// Read-only retrieval stage. It stays "unavailable" until activation returns a
// retrieval_profile_id. Runtime and readiness are rendered as separate blocks
// because one can be healthy while the other is blocked.
export function RetrievalStatusPanel({
  retrievalProfileId,
  status,
  loading,
  error,
}: RetrievalStatusPanelProps) {
  const stageState = deriveRetrievalStageState({
    retrievalProfileId,
    statusPayload: status,
  });

  return (
    <section className="panel" aria-label="Estado del perfil de retrieval">
      <div className="panel-heading">
        <div>
          <h2>Estado de retrieval</h2>
          <span>Runtime y readiness se evaluan por separado; ambos deben estar sanos.</span>
        </div>
        <span className="ui-pill">
          <Search size={13} aria-hidden="true" /> Solo lectura
        </span>
      </div>

      <div className="ui-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        {stageState.stage === "unavailable" ? (
          <div className="ui-empty" role="status">
            <span>
              Retrieval no esta disponible todavia. Aparecera cuando la activacion devuelva un
              retrieval profile.
            </span>
          </div>
        ) : null}

        {stageState.stage === "loading" || (loading && !status) ? (
          <div className="ui-hint" role="status">
            <Loader2 className="spin" size={16} /> Cargando estado del perfil...
          </div>
        ) : null}

        {status ? (
          <>
            <dl className="ui-metrics">
              <div>
                <dt>Perfil</dt>
                <dd>{status.profile.retrievalProfileId}</dd>
              </div>
              <div>
                <dt>Validacion</dt>
                <dd>{status.profile.validationStatus}</dd>
              </div>
              <div>
                <dt>Fallback lexico</dt>
                <dd>{status.profile.lexicalFallbackPolicy}</dd>
              </div>
            </dl>

            <div className="ui-state-card" aria-label="Runtime del motor de consultas">
              <span>Runtime</span>
              <div className="ui-status-row">
                <span
                  className={`ui-status-chip ${retrievalRuntimeStatusTone(
                    status.profile.lastRuntimeStatus,
                  )}`}
                >
                  {retrievalRuntimeStatusLabel(status.profile.lastRuntimeStatus)}
                </span>
                <span
                  className={
                    status.runtime.queryEngineAvailable
                      ? "ui-status-chip success"
                      : "ui-status-chip danger"
                  }
                >
                  {status.runtime.queryEngineAvailable ? (
                    <>
                      <CheckCircle2 size={13} aria-hidden="true" /> Motor disponible
                    </>
                  ) : (
                    <>
                      <Ban size={13} aria-hidden="true" /> Motor no disponible
                    </>
                  )}
                </span>
                <span className="ui-meta">
                  Vector: {status.runtime.vectorRetrievalEnabled ? "si" : "no"}
                </span>
                <span className="ui-meta">
                  Fallback: {status.runtime.lexicalFallbackAllowed ? "si" : "no"}
                </span>
              </div>
              {status.runtime.blockedReason ? (
                <span className="ui-field-note error">
                  Motivo runtime: {status.runtime.blockedReason}
                </span>
              ) : null}
            </div>

            <div className="ui-state-card" aria-label="Readiness de retrieval">
              <span>Readiness</span>
              <div className="ui-status-row">
                <span
                  className={
                    status.readiness.ready
                      ? "ui-status-chip success"
                      : "ui-status-chip danger"
                  }
                >
                  {status.readiness.ready ? (
                    <>
                      <CheckCircle2 size={13} aria-hidden="true" /> Listo
                    </>
                  ) : (
                    <>
                      <Ban size={13} aria-hidden="true" /> Bloqueado
                    </>
                  )}
                </span>
                <span className="ui-meta">
                  {status.readiness.activeVectorRows} filas activas
                </span>
              </div>
              {stageState.stage === "blocked" && stageState.blockingReasons.length > 0 ? (
                <ul className="ui-warning">
                  {stageState.blockingReasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
