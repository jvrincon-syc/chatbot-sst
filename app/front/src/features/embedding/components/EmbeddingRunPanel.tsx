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
  corpusLaunchBusy: boolean;
  corpusLaunchError: string | null;
  corpusProgress: {
    total: number;
    completed: number;
    succeeded: number;
    failed: number;
    currentLabel: string | null;
  } | null;
  onCreateRun: () => void;
  onCreateCorpusRun: () => void;
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
  corpusLaunchBusy,
  corpusLaunchError,
  corpusProgress,
  onCreateRun,
  onCreateCorpusRun,
}: EmbeddingRunPanelProps) {
  const profileSelectable = selectedProfile !== null && embeddingProfileSelectable(selectedProfile);
  const blockedReason = !selectedProfile
    ? "Selecciona un perfil de embedding."
    : !profileSelectable
      ? `El perfil ${selectedProfile.profileId} esta bloqueado para embedding de documentos.`
      : !selectedChunkBundleId
        ? "Selecciona un chunk bundle."
        : null;
  const canLaunch = blockedReason === null && !launchBusy && !corpusLaunchBusy;
  const canLaunchCorpus =
    selectedProfile !== null &&
    profileSelectable &&
    chunkBundles.length > 0 &&
    !launchBusy &&
    !corpusLaunchBusy;

  const progress = run ? embeddingRunProgressPercent(run.summary) : 0;
  const statusTone = run ? embeddingRunStatusTone(run.status) : "neutral";

  return (
    <section className="panel" aria-label="Ejecucion de embedding">
      <div className="panel-heading">
        <div>
          <h2>Ejecutar embedding</h2>
          <span>Crea un run sobre un chunk bundle con Idempotency-Key.</span>
        </div>
        <span className="ui-pill">
          <Boxes size={13} aria-hidden="true" /> Runs
        </span>
      </div>

      <div className="ui-panel-body">
        {chunkBundlesError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{chunkBundlesError}</span>
          </div>
        ) : null}

        <label className="ui-field">
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
            <span className="ui-field-note">No hay chunk bundles disponibles.</span>
          ) : null}
        </label>

        <div className="ui-actions">
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
          <button
            type="button"
            className="secondary-button"
            onClick={onCreateCorpusRun}
            disabled={!canLaunchCorpus}
            title={
              canLaunchCorpus
                ? "Crear runs de embedding para todos los chunk bundles del corpus"
                : blockedReason ?? "No hay chunk bundles disponibles"
            }
          >
            {corpusLaunchBusy ? <Loader2 className="spin" size={16} /> : <Boxes size={16} />}
            Embedding de todo el corpus
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

        {corpusLaunchError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{corpusLaunchError}</span>
          </div>
        ) : null}

        {corpusProgress ? (
          <div className="ui-warning" role="status" aria-live="polite">
            <strong>Batch del corpus</strong>
            <span>
              {corpusProgress.completed}/{corpusProgress.total} completados ·{" "}
              {corpusProgress.succeeded} exitosos · {corpusProgress.failed} fallidos
            </span>
            {corpusProgress.currentLabel ? (
              <span>Actual: {corpusProgress.currentLabel}</span>
            ) : null}
          </div>
        ) : null}

        {run ? (
          <div className="ui-panel-body" aria-label="Estado del run de embedding">
            <div className="ui-status-row">
              <span className={`ui-status-chip ${statusTone}`}>
                {embeddingRunStatusLabel(run.status)}
              </span>
              {polling ? (
                <span className="ui-meta">
                  <Loader2 className="spin" size={13} aria-hidden="true" /> Actualizando
                </span>
              ) : null}
              <span className="ui-meta">Run {run.embeddingRunId}</span>
            </div>

            <div className="ui-progress">
              <div className="ui-progress-track">
                <div className="ui-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="ui-meta" aria-live="polite">
                {run.summary.embeddedChildren}/{run.summary.requestedChildren} childs ({progress}%)
              </span>
            </div>

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
