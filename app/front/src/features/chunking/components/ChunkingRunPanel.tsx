import { Loader2, RefreshCw, Search, TriangleAlert } from "lucide-react";
import {
  chunkingRunIsTerminalStatus,
  chunkingRunProgressPercent,
  chunkingRunStatusLabel,
  chunkingRunStatusTone,
} from "../chunkingState.js";
import type { ChunkingRunSummary, ChunkingValidation } from "../chunkingTypes.js";

export function ChunkingRunPanel({
  run,
  loading,
  error,
  validation,
  validationLoading,
  validationError,
  onRefresh,
}: {
  run: ChunkingRunSummary | null;
  loading: boolean;
  error: string | null;
  validation: ChunkingValidation | null;
  validationLoading: boolean;
  validationError: string | null;
  onRefresh: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Estado de corrida</h2>
          <span>Progreso, warnings y verificacion de la ejecucion actual.</span>
        </div>
        <button className="ghost-button" type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} />
          Refrescar
        </button>
      </div>
      <div className="ui-panel-body">
        {loading ? (
          <div className="ui-empty">
            <Loader2 className="spin" size={20} />
            <span>Cargando estado de corrida...</span>
          </div>
        ) : error ? (
          <div className="ui-empty">
            <TriangleAlert size={20} />
            <span>{error}</span>
          </div>
        ) : run ? (
          <>
            <div className="ui-status-row">
              <span className={`ui-status-chip ${chunkingRunStatusTone(run.status)}`}>
                {chunkingRunStatusLabel(run.status)}
              </span>
              <span className="ui-meta">Perfil {run.profileId}</span>
              <span className="ui-meta">{run.requestedDocuments} documentos</span>
            </div>
            <div className="ui-progress">
              <div className="ui-progress-track">
                <div className="ui-progress-fill" style={{ width: `${chunkingRunProgressPercent(run)}%` }} />
              </div>
              <span>{chunkingRunProgressPercent(run)}%</span>
            </div>
            <dl className="ui-metrics">
              <div>
                <dt>Solicitados</dt>
                <dd>{run.requestedDocuments}</dd>
              </div>
              <div>
                <dt>Completados</dt>
                <dd>{run.completedDocuments}</dd>
              </div>
              <div>
                <dt>Warnings</dt>
                <dd>{run.warnings.length}</dd>
              </div>
            </dl>
            <div className="ui-links">
              <a href={run.links.self} target="_blank" rel="noreferrer">
                Ver corrida
              </a>
              <a href={run.links.documents} target="_blank" rel="noreferrer">
                Ver documentos
              </a>
              <a href={run.links.validation} target="_blank" rel="noreferrer">
                Ver validacion
              </a>
            </div>
            {run.warnings.length > 0 ? (
              <div className="ui-warning">
                <TriangleAlert size={16} />
                <ul>
                  {run.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <div className="ui-empty">
            <Search size={20} />
            <span>Sin corrida activa. Puedes inspeccionar abajo los chunks ya persistidos.</span>
          </div>
        )}
      </div>
      <div className="ui-section">
        <div className="panel-heading ui-subheading">
          <div>
            <h3>Validacion</h3>
            <span>Resumen calculado por el backend para la corrida actual.</span>
          </div>
          {validationLoading ? <Loader2 className="spin" size={16} /> : null}
        </div>
        {validationError ? (
          <div className="ui-empty compact">
            <TriangleAlert size={18} />
            <span>{validationError}</span>
          </div>
        ) : validation ? (
          <dl className="ui-metrics compact">
            <div>
              <dt>Estado</dt>
              <dd>{validation.status}</dd>
            </div>
            <div>
              <dt>Revisados</dt>
              <dd>{validation.documentsChecked}</dd>
            </div>
            <div>
              <dt>Errores</dt>
              <dd>{validation.errors}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd>{validation.warnings}</dd>
            </div>
          </dl>
        ) : (
          <div className="ui-empty compact">
            <span>
              {run && !chunkingRunIsTerminalStatus(run.status)
                ? "La validacion se publicara cuando la corrida termine."
                : "Sin validacion disponible."}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
