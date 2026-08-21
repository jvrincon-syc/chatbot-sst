import { FileText } from "lucide-react";
import { StatePanel } from "../../../components/ui/StatePanel.js";
import { StatusBadge } from "../../../components/ui/StatusBadge.js";
import type { DocumentsState } from "./useDocumentIntakeWorkspace.js";
import type { ProjectDocumentRevision } from "../platformTypes.js";

// Panel 2: read-model de revisiones registradas. Tabla densa (reusa .table-wrap):
// muestra los IDs canónicos y los estados raw/normalized/review/processing con
// badge (texto + token, nunca solo color). Checkbox por fila para elegir qué
// revisiones normalizar. Estados no-felices vía StatePanel compartido.
export function RevisionTable({
  state,
  selectedRevisionIds,
  onToggleRevision,
  onRetry,
}: {
  state: DocumentsState;
  selectedRevisionIds: ReadonlySet<string>;
  onToggleRevision: (revisionId: string) => void;
  onRetry: () => void;
}) {
  if (state.status === "no-project") {
    return (
      <StatePanel
        kind="info"
        icon={<FileText size={24} />}
        message="Selecciona un proyecto para ver sus documentos registrados."
      />
    );
  }

  if (state.status === "loading") {
    return <StatePanel kind="loading" message="Cargando revisiones..." />;
  }

  if (state.status === "error") {
    return <StatePanel kind="error" message={state.message} onRetry={onRetry} />;
  }

  if (state.status === "empty") {
    return (
      <StatePanel
        kind="info"
        icon={<FileText size={24} />}
        message="Aún no hay documentos en este proyecto. Sube un RAW para empezar."
      />
    );
  }

  return (
    <div className="table-wrap">
      <table aria-label="Revisiones de documentos del proyecto">
        <thead>
          <tr>
            <th scope="col">Seleccionar</th>
            <th scope="col">source_document_revision_id</th>
            <th scope="col">logical_document_id</th>
            <th scope="col">source_relpath</th>
            <th scope="col">RAW</th>
            <th scope="col">Normalizado</th>
            <th scope="col">review_state</th>
            <th scope="col">processing_status</th>
            <th scope="col">uploaded_at</th>
          </tr>
        </thead>
        <tbody>
          {state.revisions.map((revision) => (
            <RevisionRow
              key={revision.source_document_revision_id}
              revision={revision}
              selected={selectedRevisionIds.has(revision.source_document_revision_id)}
              onToggle={() => onToggleRevision(revision.source_document_revision_id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RevisionRow({
  revision,
  selected,
  onToggle,
}: {
  revision: ProjectDocumentRevision;
  selected: boolean;
  onToggle: () => void;
}) {
  const checkboxId = `revision-${revision.source_document_revision_id}`;
  return (
    <tr>
      <td>
        <input
          id={checkboxId}
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Seleccionar revisión ${revision.source_document_revision_id} para normalizar`}
        />
      </td>
      <td>
        <code>{revision.source_document_revision_id}</code>
      </td>
      <td>
        <code>{revision.logical_document_id}</code>
      </td>
      <td>{revision.source_relpath}</td>
      <td>
        <StatusBadge
          label={revision.raw_registered ? "Registrado" : "Sin RAW"}
          tone={revision.raw_registered ? "success" : "neutral"}
        />
      </td>
      <td>
        <StatusBadge
          label={revision.normalized_registered ? "Normalizado" : "Pendiente"}
          tone={revision.normalized_registered ? "success" : "neutral"}
        />
      </td>
      <td>
        <StatusBadge
          label={revision.review_state}
          tone={revision.review_state === "needs_review" ? "warning" : "neutral"}
        />
      </td>
      <td>
        <StatusBadge label={revision.processing_status} tone="neutral" />
      </td>
      <td>{revision.uploaded_at}</td>
    </tr>
  );
}
