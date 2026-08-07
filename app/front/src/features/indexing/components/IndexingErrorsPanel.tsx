import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { IndexingRunError } from "../indexingTypes.js";
import type { PaginatedResponse } from "../../embeddingIndexing/shared/apiTypes.js";

type IndexingErrorsPanelProps = {
  errorsPage: PaginatedResponse<IndexingRunError> | null;
  loading: boolean;
  error: string | null;
};

// Lists per-document indexing errors. It exposes internal_error_id for backend
// log correlation; it never renders stack traces or raw provider payloads.
export function IndexingErrorsPanel({ errorsPage, loading, error }: IndexingErrorsPanelProps) {
  const items = errorsPage?.items ?? [];

  return (
    <section className="panel" aria-label="Errores del run de indexing">
      <div className="panel-heading">
        <div>
          <h2>Errores de indexing</h2>
          <span>Codigo de error e identificador interno para correlacionar con logs.</span>
        </div>
        <span className="ui-meta">
          {loading ? "Cargando..." : `${errorsPage?.totalItems ?? 0} errores`}
        </span>
      </div>

      <div className="ui-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <div className="ui-note" role="status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <span>Sin errores registrados para este run.</span>
          </div>
        ) : null}

        {items.length > 0 ? (
          <ul className="ui-list" aria-label="Detalle de errores por documento">
            {items.map((item) => (
              <li key={`${item.documentId}-${item.internalErrorId ?? "na"}`} className="ui-state-card">
                <span>{item.documentId}</span>
                <strong>{item.errorCode ?? "ERROR_DESCONOCIDO"}</strong>
                <span className="ui-status-row">
                  <span className="ui-status-chip danger">{item.status}</span>
                  {item.internalErrorId ? (
                    <span className="ui-meta">error id: {item.internalErrorId}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
