import { AlertCircle, FileText, Loader2, RefreshCw } from "lucide-react";
import type {
  CandidatesState,
  EligibilityDecision,
} from "./useCorpusSnapshotWorkspace.js";
import type { ProjectDocumentRevision } from "../platformTypes.js";

// Constructor de snapshot: elige revisiones normalizadas elegibles. Una revisión
// `needs_review` exige una decisión de inclusión EXPLÍCITA (no un default oculto)
// antes de poder crear el snapshot.
export function SnapshotBuilder({
  state,
  selectedRevisionIds,
  decisions,
  pendingReviewIds,
  bulkSelectableRevisionCount,
  allBulkSelectableSelected,
  creating,
  canCreate,
  onToggleRevision,
  onSelectAllEligible,
  onClearSelection,
  onSetDecision,
  onCreate,
  onRetry,
}: {
  state: CandidatesState;
  selectedRevisionIds: ReadonlySet<string>;
  decisions: Readonly<Record<string, EligibilityDecision>>;
  pendingReviewIds: string[];
  bulkSelectableRevisionCount: number;
  allBulkSelectableSelected: boolean;
  creating: boolean;
  canCreate: boolean;
  onToggleRevision: (revisionId: string) => void;
  onSelectAllEligible: () => void;
  onClearSelection: () => void;
  onSetDecision: (revisionId: string, decision: EligibilityDecision) => void;
  onCreate: () => void;
  onRetry: () => void;
}) {
  if (state.status === "no-project") {
    return (
      <div className="ui-empty">
        <FileText size={24} />
        <span>Selecciona un proyecto para construir un snapshot de corpus.</span>
      </div>
    );
  }

  if (state.status === "loading") {
    return (
      <div className="ui-empty">
        <Loader2 className="spin" size={22} />
        <span>Cargando revisiones elegibles...</span>
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
        <FileText size={24} />
        <span>No hay revisiones normalizadas. Normaliza documentos antes de crear un snapshot.</span>
      </div>
    );
  }

  const disabledReason = creating
    ? "Creando snapshot..."
    : selectedRevisionIds.size === 0
      ? "Selecciona al menos una revisión."
      : pendingReviewIds.length > 0
        ? `Faltan decisiones de elegibilidad para ${pendingReviewIds.length} revisión(es) needs_review.`
        : null;

  return (
    <>
      <div className="platform-bulk-actions">
        <span className="ui-hint">
          {selectedRevisionIds.size} de {state.revisions.length} seleccionadas
        </span>
        <button
          className="ghost-button"
          type="button"
          onClick={onSelectAllEligible}
          disabled={bulkSelectableRevisionCount === 0 || allBulkSelectableSelected}
        >
          Seleccionar todas las elegibles
        </button>
        <button
          className="ghost-button"
          type="button"
          onClick={onClearSelection}
          disabled={selectedRevisionIds.size === 0}
        >
          Limpiar
        </button>
      </div>

      <div className="table-wrap">
        <table aria-label="Revisiones elegibles para el snapshot">
          <thead>
            <tr>
              <th scope="col">Incluir</th>
              <th scope="col">source_document_revision_id</th>
              <th scope="col">logical_document_id</th>
              <th scope="col">source_relpath</th>
              <th scope="col">review_state</th>
              <th scope="col">Decisión de elegibilidad</th>
            </tr>
          </thead>
          <tbody>
            {state.revisions.map((revision) => (
              <CandidateRow
                key={revision.source_document_revision_id}
                revision={revision}
                selected={selectedRevisionIds.has(revision.source_document_revision_id)}
                decision={decisions[revision.source_document_revision_id]}
                onToggle={() => onToggleRevision(revision.source_document_revision_id)}
                onSetDecision={(decision) =>
                  onSetDecision(revision.source_document_revision_id, decision)
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="platform-actions">
        <button
          className="primary-button"
          type="button"
          onClick={onCreate}
          disabled={!canCreate}
          title={disabledReason ?? undefined}
        >
          {creating ? <Loader2 className="spin" size={16} /> : null}
          Crear snapshot
        </button>
        {disabledReason ? (
          <span className="ui-hint" role="note">
            {disabledReason}
          </span>
        ) : null}
      </div>
    </>
  );
}

function CandidateRow({
  revision,
  selected,
  decision,
  onToggle,
  onSetDecision,
}: {
  revision: ProjectDocumentRevision;
  selected: boolean;
  decision: EligibilityDecision | undefined;
  onToggle: () => void;
  onSetDecision: (decision: EligibilityDecision) => void;
}) {
  const revisionId = revision.source_document_revision_id;
  const needsReview = revision.review_state === "needs_review";
  const checkboxId = `snapshot-${revisionId}`;
  const selectId = `decision-${revisionId}`;
  return (
    <tr>
      <td>
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Incluir revisión ${revisionId} en el snapshot`}
        />
      </td>
      <td>
        <code>{revisionId}</code>
      </td>
      <td>
        <code>{revision.logical_document_id}</code>
      </td>
      <td>{revision.source_relpath}</td>
      <td>
        <span className={`ui-status-chip ${needsReview ? "warning" : "neutral"}`}>
          {revision.review_state}
        </span>
      </td>
      <td>
        {selected && needsReview ? (
          <select
            id={selectId}
            aria-label={`Decisión de elegibilidad para ${revisionId}`}
            value={decision ?? ""}
            onChange={(event) => onSetDecision(event.target.value as EligibilityDecision)}
          >
            <option value="" disabled>
              Elegir decisión…
            </option>
            <option value="approved_after_review">Aprobar tras revisión</option>
            <option value="operator_waiver">Waiver de operador</option>
          </select>
        ) : needsReview ? (
          <span className="ui-hint">Requiere decisión al incluir</span>
        ) : (
          <span className="ui-hint">No requerida</span>
        )}
      </td>
    </tr>
  );
}
