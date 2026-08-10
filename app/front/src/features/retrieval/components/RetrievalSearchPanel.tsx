import { AlertCircle, Loader2, Search } from "lucide-react";
import type { RetrievalProfileStatus, RetrievalSearchResult } from "../retrievalTypes.js";

type RetrievalSearchPanelProps = {
  retrievalProfileId: string | null;
  status: RetrievalProfileStatus | null;
  query: string;
  onQueryChange: (value: string) => void;
  topK: number;
  onTopKChange: (value: number) => void;
  searchBusy: boolean;
  searchError: string | null;
  searchResult: RetrievalSearchResult | null;
  onSearch: () => void;
};

export function RetrievalSearchPanel({
  retrievalProfileId,
  status,
  query,
  onQueryChange,
  topK,
  onTopKChange,
  searchBusy,
  searchError,
  searchResult,
  onSearch,
}: RetrievalSearchPanelProps) {
  const blockedReason = !retrievalProfileId
    ? "Activa un bundle para obtener un retrieval profile."
    : !status
      ? "Carga el estado del perfil antes de ejecutar una consulta."
      : !status.profile.active
        ? "El perfil de retrieval seleccionado no esta activo."
        : null;
  const canSearch = blockedReason === null && !searchBusy;

  return (
    <section className="panel" aria-label="Busqueda de retrieval">
      <div className="panel-heading">
        <div>
          <h2>Busqueda de evidencia</h2>
          <span>Consulta el retrieval profile activo y revisa evidencia con procedencia.</span>
        </div>
        <span className="ui-pill">
          <Search size={13} aria-hidden="true" /> API /search
        </span>
      </div>

      <div className="ui-panel-body">
        <label className="ui-field">
          <span>Consulta</span>
          <textarea
            rows={3}
            value={query}
            onChange={(event) => onQueryChange(event.currentTarget.value)}
            placeholder="Ej. cual es el plazo maximo para responder una PQRS"
          />
        </label>

        <label className="ui-field">
          <span>Top K</span>
          <input
            type="number"
            min={1}
            max={25}
            value={topK}
            onChange={(event) => onTopKChange(Number(event.currentTarget.value) || 1)}
          />
        </label>

        <div className="ui-status-row">
          <button type="button" className="button secondary" disabled={!canSearch} onClick={onSearch}>
            {searchBusy ? (
              <>
                <Loader2 className="spin" size={16} aria-hidden="true" /> Buscando...
              </>
            ) : (
              <>
                <Search size={16} aria-hidden="true" /> Buscar evidencia
              </>
            )}
          </button>
          {blockedReason ? <span className="ui-field-note error">{blockedReason}</span> : null}
        </div>

        {searchError ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{searchError}</span>
          </div>
        ) : null}

        {searchResult ? (
          <>
            <div className="ui-hint" role="status">
              {searchResult.items.length} evidencias devueltas para {searchResult.retrievalProfileId}.
            </div>
            {searchResult.items.length === 0 ? (
              <div className="ui-empty" role="status">
                <span>No se encontro evidencia para esa consulta.</span>
              </div>
            ) : (
              <ol className="ui-list" aria-label="Resultados de retrieval">
                {searchResult.items.map((item) => (
                  <li key={`${item.nodeId}-${item.source}`} className="ui-state-card">
                    <span>
                      {item.documentId} · {item.source} · score {item.score.toFixed(3)}
                    </span>
                    <strong>{item.sectionTitle ?? item.sectionPath ?? item.childChunkId}</strong>
                    <small>
                      Paginas {item.pageStart ?? "?"}
                      {item.pageEnd && item.pageEnd !== item.pageStart ? `-${item.pageEnd}` : ""}
                    </small>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ol>
            )}
          </>
        ) : null}
      </div>
    </section>
  );
}
