import { AlertCircle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import type {
  EmbeddingBundleChunk,
  EmbeddingBundleSummary,
  EmbeddingBundleValidation,
  EmbeddingIndexingReadiness,
} from "../embeddingTypes.js";
import type { PaginatedResponse } from "../../embeddingIndexing/shared/apiTypes.js";

type EmbeddingBundleInspectorProps = {
  bundle: EmbeddingBundleSummary | null;
  loading: boolean;
  error: string | null;
  chunksPage: PaginatedResponse<EmbeddingBundleChunk> | null;
  chunksLoading: boolean;
  validation: EmbeddingBundleValidation | null;
  readiness: EmbeddingIndexingReadiness | null;
};

// Replaces the removed run-documents and run-items tables. It inspects a sealed
// embedding bundle through its bundle-level summary, per-chunk metadata,
// validation checks, and indexing readiness. It never renders vectors or paths.
export function EmbeddingBundleInspector({
  bundle,
  loading,
  error,
  chunksPage,
  chunksLoading,
  validation,
  readiness,
}: EmbeddingBundleInspectorProps) {
  return (
    <section className="panel chunking-panel" aria-label="Inspector de embedding bundle">
      <div className="panel-heading">
        <div>
          <h2>Inspeccion del bundle</h2>
          <span>Detalle a nivel de bundle y de chunk. Sin vectores ni rutas absolutas.</span>
        </div>
      </div>

      <div className="chunking-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="chunking-launch-hint" role="status">
            <Loader2 className="spin" size={16} /> Cargando bundle...
          </div>
        ) : null}

        {!loading && !error && !bundle ? (
          <div className="chunking-empty" role="status">
            <span>Un run completado mostrara aqui su embedding bundle producido.</span>
          </div>
        ) : null}

        {bundle ? (
          <>
            <dl className="chunking-mini-metrics">
              <div>
                <dt>Bundle</dt>
                <dd>{bundle.embeddingBundleId}</dd>
              </div>
              <div>
                <dt>Dimension</dt>
                <dd>{bundle.dimension}</dd>
              </div>
              <div>
                <dt>Vectores</dt>
                <dd>{bundle.vectorCount}</dd>
              </div>
            </dl>

            <div className="chunking-status-row">
              <span className="chunking-meta">Estado: {bundle.status}</span>
              <span className="chunking-meta">Validacion: {bundle.validationStatus}</span>
              <span className="chunking-meta">Readiness: {bundle.readinessStatus}</span>
            </div>

            <div className="chunking-validation">
              <div className="panel-heading chunking-subheading">
                <h2>Chunks del bundle</h2>
                <span>{chunksLoading ? "Cargando..." : `${chunksPage?.totalItems ?? 0} chunks`}</span>
              </div>
              <div className="table-wrap compact">
                <table className="chunking-table">
                  <thead>
                    <tr>
                      <th scope="col">Child chunk</th>
                      <th scope="col">Parent</th>
                      <th scope="col">Documento</th>
                      <th scope="col">Offset</th>
                      <th scope="col">Longitud</th>
                      <th scope="col">Ordinal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(chunksPage?.items ?? []).length === 0 ? (
                      <tr>
                        <td className="empty-cell" colSpan={6}>
                          {chunksLoading ? "Cargando chunks..." : "Sin chunks para mostrar."}
                        </td>
                      </tr>
                    ) : (
                      (chunksPage?.items ?? []).map((chunk) => (
                        <tr key={chunk.childChunkId}>
                          <td>{chunk.childChunkId}</td>
                          <td>{chunk.parentChunkId}</td>
                          <td>{chunk.documentId}</td>
                          <td>{chunk.vectorOffset}</td>
                          <td>{chunk.vectorLength}</td>
                          <td>{chunk.chunkOrdinal}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {validation ? (
              <div className="chunking-list" aria-label="Checks de validacion">
                {validation.checks.map((check) => (
                  <div key={check.name} className="chunking-status-row">
                    {check.passed ? (
                      <span className="chunking-status-chip success">
                        <CheckCircle2 size={13} aria-hidden="true" /> {check.name}
                      </span>
                    ) : (
                      <span className="chunking-status-chip danger">
                        <XCircle size={13} aria-hidden="true" /> {check.name}
                      </span>
                    )}
                    {check.detail ? <span className="chunking-meta">{check.detail}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}

            {readiness ? (
              <div
                className={
                  readiness.status === "ready" ? "chunking-profile-note" : "chunking-warning-box"
                }
                role="status"
              >
                <strong>Indexing readiness: {readiness.status}</strong>
                {readiness.blockingReasons.length > 0 ? (
                  <ul>
                    {readiness.blockingReasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : (
                  <span>El bundle esta listo para indexing.</span>
                )}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
