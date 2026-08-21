import { Loader2, RefreshCw } from "lucide-react";
import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import { SnapshotBuilder } from "./SnapshotBuilder.js";
import { SnapshotHistory } from "./SnapshotHistory.js";
import { useCorpusSnapshotWorkspace } from "./useCorpusSnapshotWorkspace.js";

// Composición pura del workspace de corpus snapshots: estado en el hook,
// presentación en el constructor y el historial. Aquí solo layout, topbar y notice.
export function CorpusSnapshotWorkspace() {
  const workspace = useCorpusSnapshotWorkspace();
  const loading = workspace.candidates.status === "loading";

  return (
    <main className="workspace operator-workspace platform-workspace">
      <header className="topbar">
        <div>
          <h1>Snapshots de corpus</h1>
          <p>Congela un conjunto reproducible de revisiones normalizadas del proyecto.</p>
        </div>
        <div className="topbar-actions">
          <button
            className="ghost-button"
            type="button"
            onClick={workspace.refresh}
            disabled={!workspace.projectId || loading}
          >
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Actualizar
          </button>
        </div>
      </header>

      {workspace.notice ? (
        <DashboardNotice tone={workspace.notice.tone} message={workspace.notice.message} />
      ) : null}

      <section className="corpus-grid">
        <section className="panel corpus-builder" aria-label="Constructor de snapshot">
          <div className="panel-heading">
            <div>
              <h2>Constructor</h2>
              <span>
                Elige revisiones normalizadas; una `needs_review` exige una decisión de
                elegibilidad explícita antes de entrar.
              </span>
            </div>
          </div>
          <div className="ui-panel-body">
            <SnapshotBuilder
              state={workspace.candidates}
              selectedRevisionIds={workspace.selectedRevisionIds}
              decisions={workspace.decisions}
              pendingReviewIds={workspace.pendingReviewIds}
              creating={workspace.creating}
              canCreate={workspace.canCreate}
              onToggleRevision={workspace.toggleRevision}
              onSetDecision={workspace.setDecision}
              onCreate={workspace.createSnapshot}
              onRetry={workspace.refresh}
            />
          </div>
        </section>

        <section className="panel corpus-history" aria-label="Historial de snapshots">
          <div className="panel-heading">
            <div>
              <h2>Historial</h2>
              <span>Snapshots inmutables; el seleccionado se rehidrata tras un refresh.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <SnapshotHistory
              state={workspace.history}
              selectedSnapshotId={workspace.selectedSnapshotId}
            />
          </div>
        </section>
      </section>
    </main>
  );
}
