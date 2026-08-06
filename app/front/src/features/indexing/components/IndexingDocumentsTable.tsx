import { AlertCircle, CheckCircle2, Clock3, Loader2 } from "lucide-react";
import { indexingDocumentIsCommitted } from "../indexingState.js";
import type { IndexingRunDocument } from "../indexingTypes.js";
import type { PaginatedResponse } from "../../embeddingIndexing/shared/apiTypes.js";

type IndexingDocumentsTableProps = {
  documentsPage: PaginatedResponse<IndexingRunDocument> | null;
  loading: boolean;
  error: string | null;
};

// Shows the documents of an indexing run. A document only counts as indexed when
// it has a commit timestamp; that distinction is surfaced explicitly, not by
// color alone.
export function IndexingDocumentsTable({
  documentsPage,
  loading,
  error,
}: IndexingDocumentsTableProps) {
  const items = documentsPage?.items ?? [];

  return (
    <section className="panel chunking-panel" aria-label="Documentos del run de indexing">
      <div className="panel-heading">
        <div>
          <h2>Documentos indexados</h2>
          <span>Un documento cuenta como indexado solo con fecha de commit.</span>
        </div>
        <span className="chunking-meta">
          {loading ? "Cargando..." : `${documentsPage?.totalItems ?? 0} documentos`}
        </span>
      </div>

      <div className="chunking-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="table-wrap compact">
          <table className="chunking-table">
            <thead>
              <tr>
                <th scope="col">Documento</th>
                <th scope="col">Estado</th>
                <th scope="col">Elegibilidad</th>
                <th scope="col">Vectores</th>
                <th scope="col">Indexado</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td className="empty-cell" colSpan={5}>
                    {loading ? "Cargando documentos..." : "Sin documentos para mostrar."}
                  </td>
                </tr>
              ) : (
                items.map((document) => {
                  const committed = indexingDocumentIsCommitted(document);
                  return (
                    <tr key={document.documentId}>
                      <td>
                        <div className="chunking-row-cell">
                          <strong>{document.documentId}</strong>
                          <span>{document.sourceRelpath}</span>
                        </div>
                      </td>
                      <td>{document.status}</td>
                      <td>
                        <div className="chunking-row-cell">
                          <strong>{document.eligibilityStatus}</strong>
                          <span>{document.eligibilityReason}</span>
                        </div>
                      </td>
                      <td>{document.vectorCount}</td>
                      <td>
                        {committed ? (
                          <span className="chunking-status-chip success">
                            <CheckCircle2 size={13} aria-hidden="true" /> Indexado
                          </span>
                        ) : (
                          <span className="chunking-status-chip warning">
                            {loading ? (
                              <Loader2 className="spin" size={13} aria-hidden="true" />
                            ) : (
                              <Clock3 size={13} aria-hidden="true" />
                            )}{" "}
                            Sin commit
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
