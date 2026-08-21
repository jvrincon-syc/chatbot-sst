import { AlertCircle, Ban, CheckCircle2, Grid3x3, Loader2, RefreshCw } from "lucide-react";
import type { MatrixState } from "./useVariantMatrixWorkspace.js";
import type { VariantMatrixCell } from "../platformTypes.js";

// Presentación pura de la matriz de recetas. Cada celda es una tarjeta-receta
// (no una fila de tabla densa): construible = seleccionable con teclado; bloqueada
// = tarjeta inerte que muestra su motivo en TEXTO, no solo por color (a11y).
export function VariantMatrixTable({
  state,
  selectedCellId,
  onSelectCell,
  onRetry,
}: {
  state: MatrixState;
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
  onRetry: () => void;
}) {
  if (state.status === "no-project") {
    return (
      <div className="ui-empty">
        <Grid3x3 size={24} />
        <span>Selecciona un proyecto para ver su matriz de recetas construibles.</span>
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <div className="ui-empty">
        <Loader2 className="spin" size={22} />
        <span>Cargando matriz de recetas...</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="ui-empty">
        <AlertCircle size={24} />
        <span role="alert">{state.message}</span>
        <button className="secondary-button" type="button" onClick={onRetry}>
          <RefreshCw size={16} />
          Reintentar
        </button>
      </div>
    );
  }

  if (state.status === "empty") {
    return (
      <div className="ui-empty">
        <Grid3x3 size={24} />
        <span>
          La configuración vigente no produce celdas de receta. Ajusta perfiles o bindings del
          proyecto para habilitar variantes.
        </span>
      </div>
    );
  }

  return (
    <ul className="variant-matrix" aria-label="Celdas de receta">
      {state.cells.map((cell) => (
        <li key={cell.cell_id}>
          {cell.buildable ? (
            <BuildableCell
              cell={cell}
              selected={cell.cell_id === selectedCellId}
              onSelect={() => onSelectCell(cell.cell_id)}
            />
          ) : (
            <BlockedCell cell={cell} />
          )}
        </li>
      ))}
    </ul>
  );
}

function BuildableCell({
  cell,
  selected,
  onSelect,
}: {
  cell: VariantMatrixCell;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={selected ? "variant-cell selected" : "variant-cell"}
      aria-pressed={selected}
      aria-label={`Seleccionar celda ${cell.target_binding_key}`}
      onClick={onSelect}
    >
      <CellHeader cell={cell} />
      <CellDimensions cell={cell} />
      <span className="variant-cell-status buildable">
        <CheckCircle2 size={14} />
        Construible
      </span>
    </button>
  );
}

function BlockedCell({ cell }: { cell: VariantMatrixCell }) {
  return (
    <div className="variant-cell blocked" aria-disabled="true">
      <CellHeader cell={cell} />
      <CellDimensions cell={cell} />
      <span className="variant-cell-status blocked">
        <Ban size={14} />
        {/* El motivo se muestra en texto: el estado no se comunica solo por color. */}
        Bloqueada: {cell.blocked_reason ?? "no construible con la configuración vigente"}
      </span>
    </div>
  );
}

function CellHeader({ cell }: { cell: VariantMatrixCell }) {
  return (
    <div className="variant-cell-head">
      <strong>{cell.target_binding_key}</strong>
      {/* Badge de linaje, coherente con "Config v{n}" del workspace de proyectos. */}
      <span
        className="ui-pill"
        aria-label={`Versión de configuración ${cell.configuration_version}`}
      >
        Config v{cell.configuration_version}
      </span>
    </div>
  );
}

function CellDimensions({ cell }: { cell: VariantMatrixCell }) {
  return (
    <dl className="variant-cell-dims">
      <div>
        <dt>Processing</dt>
        <dd>{cell.processing_profile_id}</dd>
      </div>
      <div>
        <dt>Chunking</dt>
        <dd>{cell.chunking_profile_id}</dd>
      </div>
      <div>
        <dt>Embedding</dt>
        <dd>{cell.embedding_profile_id}</dd>
      </div>
    </dl>
  );
}
