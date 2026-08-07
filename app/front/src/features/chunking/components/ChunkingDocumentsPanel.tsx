import { Loader2, SplitSquareHorizontal, TriangleAlert } from "lucide-react";
import { PaginationBar } from "./PaginationBar.js";

export function ChunkingDocumentsPanel({
  title,
  subtitle,
  rows,
  page,
  totalPages,
  loading,
  error,
  selectedDocumentId,
  primaryHeader,
  secondaryHeader,
  emptyMessage,
  onSelectDocument,
  onPageChange,
}: {
  title: string;
  subtitle: string;
  rows: Array<{
    documentId: string;
    normalizedRelpath: string;
    primaryValue: string;
    secondaryValue: string;
  }>;
  page: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
  selectedDocumentId: string | null;
  primaryHeader: string;
  secondaryHeader: string;
  emptyMessage: string;
  onSelectDocument: (documentId: string) => void;
  onPageChange: (page: number) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <span>{subtitle}</span>
        </div>
      </div>
      {loading ? (
        <div className="ui-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando documentos...</span>
        </div>
      ) : error ? (
        <div className="ui-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : rows.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="ui-table">
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>{primaryHeader}</th>
                  <th>{secondaryHeader}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((document) => (
                  <tr
                    key={document.documentId}
                    className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                  >
                    <td>
                      <div className="ui-row-cell">
                        <strong>{document.documentId}</strong>
                        <span>{document.normalizedRelpath}</span>
                        <button type="button" className="row-detail-button" onClick={() => onSelectDocument(document.documentId)}>
                          Inspeccionar
                        </button>
                      </div>
                    </td>
                    <td>{document.primaryValue}</td>
                    <td>{document.secondaryValue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="ui-empty">
          <SplitSquareHorizontal size={20} />
          <span>{emptyMessage}</span>
        </div>
      )}
    </section>
  );
}
