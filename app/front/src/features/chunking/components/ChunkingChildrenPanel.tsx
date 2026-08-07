import { ArrowRight, Loader2, TriangleAlert } from "lucide-react";
import { PaginationBar } from "./PaginationBar.js";
import type { ChunkingChildrenPage, ChunkingParentsPage } from "../chunkingTypes.js";

export function ChunkingChildrenPanel({
  parent,
  childrenPage,
  loading,
  error,
  onPageChange,
}: {
  parent: ChunkingParentsPage["items"][number] | null;
  childrenPage: ChunkingChildrenPage | null;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
}) {
  const page = childrenPage?.page ?? 1;
  const totalPages = childrenPage?.totalPages ?? 0;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Children</h2>
          <span>{parent ? parent.chunkId : "Selecciona un parent para continuar."}</span>
        </div>
      </div>
      {loading ? (
        <div className="ui-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando children...</span>
        </div>
      ) : error ? (
        <div className="ui-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : childrenPage && childrenPage.items.length > 0 ? (
        <>
          <div className="ui-list compact">
            {childrenPage.items.map((child) => (
              <article key={child.chunkId} className="ui-list-card">
                <div className="chunking-child-header">
                  <strong>
                    #{child.ordinal} · {child.chunkId}
                  </strong>
                  <span>{child.tokenCount} tokens</span>
                </div>
                <p>{child.text.slice(0, 240) || "(sin texto)"}</p>
                <div className="chunking-child-meta">
                  <span>
                    Overlap prev {child.overlapPreviousTokens} / next {child.overlapNextTokens}
                  </span>
                  <span>
                    Paginas {child.sourceSpan.pageStart ?? "?"}-{child.sourceSpan.pageEnd ?? "?"}
                  </span>
                </div>
                {child.zeroOverlapReasons.length > 0 ? (
                  <div className="chunking-child-warning">
                    <TriangleAlert size={14} />
                    <span>{child.zeroOverlapReasons.join(", ")}</span>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="ui-empty">
          <ArrowRight size={20} />
          <span>Sin children disponibles para el parent seleccionado.</span>
        </div>
      )}
    </section>
  );
}
