import { Blocks, CheckCircle2, Settings2, TriangleAlert } from "lucide-react";
import { MetricCard } from "../../components/ui/MetricCard.js";
import { DashboardNotice } from "../dashboard/components/DashboardChrome.js";
import { ChunkingChildrenPanel } from "./components/ChunkingChildrenPanel.js";
import { ChunkingDocumentsPanel } from "./components/ChunkingDocumentsPanel.js";
import { ChunkingLaunchPanel } from "./components/ChunkingLaunchPanel.js";
import { ChunkingParentsPanel } from "./components/ChunkingParentsPanel.js";
import { ChunkingProfilePanel } from "./components/ChunkingProfilePanel.js";
import { ChunkingRunPanel } from "./components/ChunkingRunPanel.js";
import { chunkingRunStatusLabel, chunkingRunStatusTone } from "./chunkingState.js";
import { useChunkingWorkspace } from "./useChunkingWorkspace.js";

// Solo compone: el estado vive en useChunkingWorkspace y la presentacion en
// los paneles de ./components.
export function ChunkingWorkspace() {
  const workspace = useChunkingWorkspace();

  return (
    <section className="chunking-workspace">
      {workspace.notice ? (
        <DashboardNotice tone={workspace.notice.tone} message={workspace.notice.message} />
      ) : null}

      <section className="chunking-hero">
        <ChunkingLaunchPanel
          form={workspace.form}
          profiles={workspace.profiles}
          profilesError={workspace.profilesError}
          profilesLoading={workspace.profilesLoading}
          parsedDocumentIds={workspace.parsedDocumentIds}
          selectedProfile={workspace.selectedProfile}
          busy={workspace.launchBusy}
          onChange={workspace.updateForm}
          onLaunch={workspace.handleLaunchRun}
          onRegenerateKey={workspace.regenerateIdempotencyKey}
        />
        <ChunkingProfilePanel
          profile={workspace.selectedProfile}
          profilesLoading={workspace.profilesLoading}
          status={workspace.runSummary}
          runLoading={workspace.runLoading}
          onRefresh={workspace.handleRefresh}
        />
      </section>

      <section className="chunking-summary-grid">
        <MetricCard
          label="Corrida activa"
          value={workspace.runSummary?.runId ?? "sin corrida"}
          tone="neutral"
          icon={<Blocks size={18} />}
        />
        <MetricCard
          label="Estado"
          value={
            workspace.runSummary ? chunkingRunStatusLabel(workspace.runSummary.status) : "sin estado"
          }
          tone={chunkingRunStatusTone(workspace.runSummary?.status ?? "queued")}
          icon={<CheckCircle2 size={18} />}
        />
        <MetricCard
          label="Progreso"
          value={`${workspace.runProgress}%`}
          tone={workspace.runProgress === 100 ? "success" : "warning"}
          icon={<Settings2 size={18} />}
        />
        <MetricCard
          label="Validation"
          value={workspace.validationValue}
          tone={
            workspace.validation?.status === "passed"
              ? "success"
              : workspace.validationValue === "pendiente"
                ? "neutral"
                : "warning"
          }
          icon={<TriangleAlert size={18} />}
        />
      </section>

      <section className="chunking-grid">
        <ChunkingRunPanel
          run={workspace.runSummary}
          loading={workspace.runLoading}
          error={workspace.runError}
          validation={workspace.validation}
          validationLoading={workspace.validationLoading}
          validationError={workspace.validationError}
          onRefresh={workspace.handleRefresh}
        />
        <ChunkingDocumentsPanel
          title={workspace.documentPanelTitle}
          subtitle={workspace.documentPanelSubtitle}
          rows={workspace.documentRows}
          page={workspace.documentPanelPage?.page ?? 1}
          totalPages={workspace.documentPanelPage?.totalPages ?? 0}
          loading={workspace.documentPanelLoading}
          error={workspace.documentPanelError}
          selectedDocumentId={workspace.selectedDocumentId}
          primaryHeader={workspace.documentPrimaryHeader}
          secondaryHeader={workspace.documentSecondaryHeader}
          emptyMessage={
            workspace.isRunMode
              ? "No hay documentos para mostrar."
              : "No se encontraron documentos con chunks persistidos."
          }
          onSelectDocument={workspace.handleSelectDocument}
          onPageChange={workspace.handleDocumentPageChange}
        />
      </section>

      <section className="chunking-inspector-grid">
        <ChunkingParentsPanel
          documentId={workspace.selectedDocumentId}
          parentsPage={workspace.parentsPage}
          loading={workspace.parentsLoading}
          error={workspace.parentsError}
          selectedParentId={workspace.selectedParentId}
          onSelectParent={workspace.handleSelectParent}
          onPageChange={workspace.handleParentsPageChange}
        />
        <ChunkingChildrenPanel
          parent={workspace.selectedParent}
          childrenPage={workspace.childrenPage}
          loading={workspace.childrenLoading}
          error={workspace.childrenError}
          onPageChange={workspace.handleChildrenPageChange}
        />
      </section>
    </section>
  );
}
