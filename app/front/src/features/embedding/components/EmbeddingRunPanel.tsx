import { AlertCircle, Boxes, Loader2, Play } from "lucide-react";
import {
  embeddingProfileSelectable,
  embeddingRunProgressPercent,
  embeddingRunStatusLabel,
  embeddingRunStatusTone,
} from "../embeddingState.js";
import type {
  EmbeddingChunkBundleListItem,
  EmbeddingProfile,
  EmbeddingRun,
} from "../embeddingTypes.js";

type EmbeddingRunPanelProps = {
  selectedProfile: EmbeddingProfile | null;
  chunkBundles: EmbeddingChunkBundleListItem[];
  chunkBundlesLoading: boolean;
  chunkBundlesError: string | null;
  selectedChunkBundleId: string | null;
  onSelectChunkBundle: (chunkBundleId: string) => void;
  run: EmbeddingRun | null;
  polling: boolean;
  launchBusy: boolean;
  launchError: string | null;
  onCreateRun: () => void;
};

const CHUNK_BUNDLE_LABEL_ID = "embedding-chunk-bundle-label";

// Drives creation and progress of an embedding run over a chunk bundle. The
// launch action stays disabled with a visible reason whenever the selected
// profile is not enabled for document embedding.
export function EmbeddingRunPanel({
  selectedProfile,
  chunkBundles,
  chunkBundlesLoading,
  chunkBundlesError,
  selectedChunkBundleId,
  onSelectChunkBundle,
  run,
  polling,
  launchBusy,
  launchError,
  onCreateRun,
}: EmbeddingRunPanelProps) {
  const profileSelectable = selectedProfile !== null && embeddingProfileSelectable(selectedProfile);
  const blockedReason = !selectedProfile
    ? "Selecciona un perfil de embedding."
    : !profileSelectable
      ? `El perfil ${selectedProfile.profileId} esta bloqueado para embedding de documentos.`
      : !selectedChunkBundleId
        ? "Selecciona un chunk bundle."
        : null;
  const canLaunch = blockedReason === null && !launchBusy;

  const progress = run ? embeddingRunProgressPercent(run.summary) : 0;
  const statusTone = run ? embeddingRunStatusTone(run.status) : "neutral";

  return (
    <section className="panel chunking-panel" aria-label="Ejecucion de embedding">
      <div className="panel-heading">
        <div>
          <h2>Ejecutar embedding</h2>
          <span>Crea un run sobre un chunk bundle con Idempotency-Key.</span>
        </div>
        <span className="chunking-pill">
          <Boxes size={13} aria-hidden="true" /> Runs
        </span>
      </div>

      <div className="chunking-panel-body">
        {chunkBundlesError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{chunkBundlesError}</span>
          </div>
        ) : null}

        <label className="chunking-field">
          <span id={CHUNK_BUNDLE_LABEL_ID}>Chunk bundle</span>
          <select
            aria-labelledby={CHUNK_BUNDLE_LABEL_ID}
            value={selectedChunkBundleId ?? ""}
            disabled={chunkBundlesLoading || chunkBundles.length === 0}
            onChange={(event) => onSelectChunkBundle(event.currentTarget.value)}
          >
            <option value="" disabled>
              {chunkBundlesLoading ? "Cargando chunk bundles..." : "Selecciona un chunk bundle"}
            </option>
            {chunkBundles.map((bundle) => (
              <option key={bundle.chunkBundleId} value={bundle.chunkBundleId}>
                {bundle.chunkBundleId} · {bundle.status} · {bundle.childCount} childs
              </option>
            ))}
          </select>
          {!chunkBundlesLoading && chunkBundles.length === 0 ? (
            <span className="chunking-field-note">No hay chunk bundles disponibles.</span>
          ) : null}
        </label>

        <div className="chunking-launch-actions">
          <button
            type="button"
            className="primary-button"
            onClick={onCreateRun}
            disabled={!canLaunch}
            title={blockedReason ?? "Crear run de embedding"}
          >
            {launchBusy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Ejecutar embedding
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
          <div className="chunking-panel-body" aria-label="Estado del run de embedding">
            <div className="chunking-status-row">
              <span className={`chunking-status-chip ${statusTone}`}>
                {embeddingRunStatusLabel(run.status)}
              </span>
              {polling ? (
                <span className="chunking-meta">
                  <Loader2 className="spin" size={13} aria-hidden="true" /> Actualizando
                </span>
              ) : null}
              <span className="chunking-meta">Run {run.embeddingRunId}</span>
            </div>

            <div className="chunking-progress">
              <div className="chunking-progress-track">
                <div className="chunking-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="chunking-meta" aria-live="polite">
                {run.summary.embeddedChildren}/{run.summary.requestedChildren} childs ({progress}%)
              </span>
            </div>

            {run.warnings.length > 0 ? (
              <div className="chunking-warning-box" role="status">
                <strong>Advertencias</strong>
                <ul>
                  {run.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {run.errorSummary ? (
              <div className="notice notice-danger" role="alert">
                <AlertCircle size={16} />
                <span>{run.errorSummary}</span>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
