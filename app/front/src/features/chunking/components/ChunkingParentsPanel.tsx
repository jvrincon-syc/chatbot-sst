import { Loader2, Search, TriangleAlert } from "lucide-react";
import { PaginationBar } from "./PaginationBar.js";
import type { ChunkingParentsPage } from "../chunkingTypes.js";

export function ChunkingParentsPanel({
  documentId,
  parentsPage,
  loading,
  error,
  selectedParentId,
  onSelectParent,
  onPageChange,
}: {
  documentId: string | null;
  parentsPage: ChunkingParentsPage | null;
  loading: boolean;
  error: string | null;
  selectedParentId: string | null;
  onSelectParent: (parentId: string) => void;
  onPageChange: (page: number) => void;
}) {
  const page = parentsPage?.page ?? 1;
  const totalPages = parentsPage?.totalPages ?? 0;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Parents</h2>
          <span>{documentId ?? "Selecciona un documento para inspeccionar."}</span>
        </div>
      </div>
      {loading ? (
        <div className="ui-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando parents...</span>
        </div>
      ) : error ? (
        <div className="ui-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : parentsPage && parentsPage.items.length > 0 ? (
        <>
          <div className="ui-list">
            {parentsPage.items.map((parent) => (
              <button
                key={parent.chunkId}
                type="button"
                className={selectedParentId === parent.chunkId ? "ui-list-item active" : "ui-list-item"}
                onClick={() => onSelectParent(parent.chunkId)}
              >
                <strong>
                  #{parent.ordinal} · {parent.chunkId}
                </strong>
                <span>{parent.text.slice(0, 160) || "(sin texto)"}</span>
                <small>
                  Paginas {parent.sourceSpan.pageStart ?? "?"}-{parent.sourceSpan.pageEnd ?? "?"}
                </small>
              </button>
            ))}
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="ui-empty">
          <Search size={20} />
          <span>Sin parents disponibles para el documento seleccionado.</span>
        </div>
      )}
    </section>
  );
}
