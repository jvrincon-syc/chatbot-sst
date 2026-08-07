import { AlertCircle, Loader2, Play, Workflow } from "lucide-react";
import {
  indexingRunProgressPercent,
  indexingRunStatusLabel,
  indexingRunStatusTone,
} from "../indexingState.js";
import type { IndexingRun } from "../indexingTypes.js";

type IndexingRunPanelProps = {
  embeddingBundleId: string | null;
  embeddingBundleReady: boolean;
  bundleFirstEnabled: boolean;
  run: IndexingRun | null;
  polling: boolean;
  launchBusy: boolean;
  launchError: string | null;
  onCreateRun: () => void;
};

// Creates and tracks an indexing run over a single embedding bundle. It never
// exposes target/provider/dimension/consumer-scope choices; those are
// server-resolved. Activation lives in its own panel, not here.
export function IndexingRunPanel({
  embeddingBundleId,
  embeddingBundleReady,
  bundleFirstEnabled,
  run,
  polling,
  launchBusy,
  launchError,
  onCreateRun,
}: IndexingRunPanelProps) {
  const blockedReason = !embeddingBundleId
    ? "Primero completa un run de embedding con un bundle producido."
    : !embeddingBundleReady
      ? "El embedding bundle todavia no esta listo para indexing."
      : !bundleFirstEnabled
        ? "El flag indexing_bundle_first esta apagado en el backend."
        : null;
  const canLaunch = blockedReason === null && !launchBusy;

  const progress = run ? indexingRunProgressPercent(run.summary) : 0;
  const statusTone = run ? indexingRunStatusTone(run.status) : "neutral";

  return (
    <section className="panel" aria-label="Ejecucion de indexing">
      <div className="panel-heading">
        <div>
          <h2>Ejecutar indexing</h2>
          <span>Publica el embedding bundle al target compatible resuelto por el servidor.</span>
        </div>
        <span className="ui-pill">
          <Workflow size={13} aria-hidden="true" /> Runs
        </span>
      </div>

      <div className="ui-panel-body">
        <dl className="ui-metrics compact">
          <div>
            <dt>Embedding bundle</dt>
            <dd>{embeddingBundleId ?? "Sin bundle"}</dd>
          </div>
          <div>
            <dt>Target</dt>
            <dd>Resuelto por el servidor</dd>
          </div>
        </dl>

        <div className="ui-actions">
          <button
            type="button"
            className="primary-button"
            onClick={onCreateRun}
            disabled={!canLaunch}
            title={blockedReason ?? "Crear run de indexing"}
          >
            {launchBusy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Ejecutar indexing
          </button>
          {blockedReason ? (
            <span className="pipeline-action-alert" role="status">
              <AlertCircle size={14} aria-hidden="true" />
              {blockedReason}
            </span>
          ) : null}
        </div>

        {launchError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{launchError}</span>
          </div>
        ) : null}

        {run ? (
          <div className="ui-panel-body" aria-label="Estado del run de indexing">
            <div className="ui-status-row">
              <span className={`ui-status-chip ${statusTone}`}>
                {indexingRunStatusLabel(run.status)}
              </span>
              {polling ? (
                <span className="ui-meta">
                  <Loader2 className="spin" size={13} aria-hidden="true" /> Actualizando
                </span>
              ) : null}
              <span className="ui-meta">Validacion: {run.validationStatus}</span>
              <span className="ui-meta">Activacion: {run.activationStatus}</span>
              <span className="ui-meta">Run {run.runId}</span>
            </div>

            <div className="ui-progress">
              <div className="ui-progress-track">
                <div className="ui-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="ui-meta" aria-live="polite">
                {run.summary.committedDocuments}/{run.summary.requestedDocuments} documentos ({progress}
                %)
              </span>
            </div>

            {run.summary.interrupted ? (
              <div className="ui-warning" role="status">
                <strong>Run interrumpido</strong>
                <span>El run se reconcilio como interrumpido; revisa documentos y errores.</span>
              </div>
            ) : null}

            {run.warnings.length > 0 ? (
              <div className="ui-warning" role="status">
                <strong>Advertencias</strong>
                <ul>
                  {run.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
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
