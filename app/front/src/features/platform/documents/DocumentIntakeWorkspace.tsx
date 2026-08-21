import { AlertTriangle, CheckCircle2, FileCheck2, FileStack, Loader2, RefreshCw } from "lucide-react";
import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import { MetricCard } from "../../../components/ui/MetricCard.js";
import { RawUploadPanel } from "./RawUploadPanel.js";
import { RevisionTable } from "./RevisionTable.js";
import { NormalizationPanel } from "./NormalizationPanel.js";
import { useDocumentIntakeWorkspace } from "./useDocumentIntakeWorkspace.js";

// Composición pura del workspace de intake documental: estado en el hook,
// presentación en los tres paneles (subir RAW, revisiones, normalizar). Aquí solo
// layout, topbar, resumen y notice.
export function DocumentIntakeWorkspace() {
  const workspace = useDocumentIntakeWorkspace();
  const loading = workspace.documents.status === "loading";
  // Resumen de procedencia derivado del read-model ya cargado (sin fetch extra).
  const revisions =
    workspace.documents.status === "ready" ? workspace.documents.revisions : [];
  const normalizedCount = revisions.filter((r) => r.normalized_registered).length;
  const needsReviewCount = revisions.filter((r) => r.review_state === "needs_review").length;

  return (
    <main className="workspace operator-workspace platform-workspace">
      <header className="topbar">
        <div>
          <h1>Intake documental</h1>
          <p>Lleva documentos desde RAW hasta normalizados dentro del proyecto.</p>
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

      {revisions.length > 0 ? (
        <section className="document-summary" aria-label="Resumen de intake">
          <MetricCard
            label="Documentos"
            value={revisions.length}
            icon={<FileStack size={18} />}
            tone="neutral"
          />
          <MetricCard
            label="RAW registrados"
            value={revisions.filter((r) => r.raw_registered).length}
            icon={<FileCheck2 size={18} />}
            tone="neutral"
          />
          <MetricCard
            label="Normalizados"
            value={normalizedCount}
            icon={<CheckCircle2 size={18} />}
            tone={normalizedCount > 0 ? "success" : "neutral"}
          />
          <MetricCard
            label="Requieren revisión"
            value={needsReviewCount}
            icon={<AlertTriangle size={18} />}
            tone={needsReviewCount > 0 ? "warning" : "neutral"}
          />
        </section>
      ) : null}

      <section className="document-grid">
        <div className="document-aside">
          <RawUploadPanel
            disabled={!workspace.projectId}
            uploading={workspace.uploading}
            lastUploadedRevisionId={workspace.lastUploadedRevisionId}
            onUpload={workspace.upload}
          />
          <NormalizationPanel
            variants={workspace.variants}
            selectedVariantId={workspace.selectedVariantId}
            selectedCount={workspace.selectedRevisionIds.size}
            force={workspace.force}
            normalizing={workspace.normalizing}
            canNormalize={workspace.canNormalize}
            report={workspace.report}
            onSelectVariant={workspace.selectVariant}
            onToggleForce={workspace.toggleForce}
            onNormalize={workspace.normalize}
          />
        </div>

        <section className="panel document-main" aria-label="Revisiones registradas">
          <div className="panel-heading">
            <div>
              <h2>Revisiones registradas</h2>
              <span>Marca las revisiones a normalizar; los estados usan texto además de color.</span>
            </div>
            {revisions.length > 0 ? (
              <div className="document-select-actions">
                <span className="ui-hint">
                  {workspace.selectedRevisionIds.size} de {revisions.length} seleccionadas
                </span>
                <button
                  className="ghost-button"
                  type="button"
                  onClick={workspace.selectAllRevisions}
                  disabled={
                    workspace.bulkSelectableRevisionCount === 0 || workspace.allBulkSelectableSelected
                  }
                >
                  Seleccionar todos
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  onClick={workspace.clearRevisionSelection}
                  disabled={workspace.selectedRevisionIds.size === 0}
                >
                  Limpiar
                </button>
              </div>
            ) : null}
          </div>
          <div className="ui-panel-body">
            <RevisionTable
              state={workspace.documents}
              selectedRevisionIds={workspace.selectedRevisionIds}
              onToggleRevision={workspace.toggleRevision}
              onRetry={workspace.refresh}
            />
          </div>
        </section>
      </section>
    </main>
  );
}
