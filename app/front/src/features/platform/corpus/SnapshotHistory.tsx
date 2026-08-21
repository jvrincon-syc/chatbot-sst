import { AlertCircle, History, Loader2 } from "lucide-react";
import type { HistoryState } from "./useCorpusSnapshotWorkspace.js";

// Historial de snapshots del proyecto (read-model rehidratable). Marca el snapshot
// seleccionado (persistido como ID de navegación) para que sobreviva a un refresh.
// `manifest_hash` es la firma inmutable de procedencia del snapshot.
export function SnapshotHistory({
  state,
  selectedSnapshotId,
}: {
  state: HistoryState;
  selectedSnapshotId: string | null;
}) {
  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className="ui-empty">
        <Loader2 className="spin" size={20} />
        <span>Cargando historial...</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="ui-empty">
        <AlertCircle size={22} />
        <span role="alert">{state.message}</span>
      </div>
    );
  }

  if (state.status === "empty") {
    return (
      <div className="ui-empty">
        <History size={22} />
        <span>Este proyecto aún no tiene snapshots. Crea el primero desde el constructor.</span>
      </div>
    );
  }

  return (
    <ul className="ui-list" aria-label="Historial de snapshots de corpus">
      {state.snapshots.map((snapshot) => {
        const active = snapshot.corpus_snapshot_id === selectedSnapshotId;
        return (
          <li key={snapshot.corpus_snapshot_id}>
            <div
              className={active ? "ui-list-item active" : "ui-list-item"}
              aria-current={active ? "true" : undefined}
            >
              <strong>
                <code>{snapshot.corpus_snapshot_id}</code>
              </strong>
              <span>
                {snapshot.document_count} doc(s) · manifest{" "}
                <code title="Firma inmutable de procedencia">{snapshot.manifest_hash}</code>
              </span>
              <small>{snapshot.created_at}</small>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
