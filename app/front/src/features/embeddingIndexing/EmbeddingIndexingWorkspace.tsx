import { EmbeddingCatalogPanel } from "../embedding/components/EmbeddingCatalogPanel.js";
import { EmbeddingRunPanel } from "../embedding/components/EmbeddingRunPanel.js";
import { EmbeddingBundleInspector } from "../embedding/components/EmbeddingBundleInspector.js";
import { IndexingRunPanel } from "../indexing/components/IndexingRunPanel.js";
import { IndexingDocumentsTable } from "../indexing/components/IndexingDocumentsTable.js";
import { IndexingErrorsPanel } from "../indexing/components/IndexingErrorsPanel.js";
import { ActivationPanel } from "../indexing/components/ActivationPanel.js";
import { RetrievalProfilesPanel } from "../retrieval/components/RetrievalProfilesPanel.js";
import { RetrievalStatusPanel } from "../retrieval/components/RetrievalStatusPanel.js";
import { RetrievalValidationPanel } from "../retrieval/components/RetrievalValidationPanel.js";
import { PipelineHeader } from "./PipelineHeader.js";
import { PipelineSummary } from "./PipelineSummary.js";
import { PipelineHandoffPanel } from "./PipelineHandoffPanel.js";
import { useEmbeddingIndexingPipeline } from "./useEmbeddingIndexingPipeline.js";
import { deriveStageStatus } from "./pipelineStageStatus.js";
import type {
  EmbeddingIndexingStage,
  EmbeddingIndexingState,
} from "../dashboard/dashboardTypes.js";

type EmbeddingIndexingWorkspaceProps = {
  activeStage: EmbeddingIndexingStage;
  embeddingIndexingState: EmbeddingIndexingState;
  onStageChange: (stage: EmbeddingIndexingStage) => void;
  onEmbeddingIndexingStateChange: (patch: Partial<EmbeddingIndexingState>) => void;
};

// Unified workspace for the bundle-first pipeline. It composes the feature
// panels for each stage and delegates all data work to the pipeline hook, so it
// stays a thin orchestrator rather than a monolith.
export function EmbeddingIndexingWorkspace({
  activeStage,
  embeddingIndexingState,
  onStageChange,
  onEmbeddingIndexingStateChange,
}: EmbeddingIndexingWorkspaceProps) {
  const pipeline = useEmbeddingIndexingPipeline({
    persistedState: embeddingIndexingState,
    onPersistedStateChange: onEmbeddingIndexingStateChange,
  });
  const { embedding, indexing, activation, retrieval } = pipeline;

  const stageStatus = deriveStageStatus({
    embeddingRunStatus: embedding.run?.status ?? null,
    embeddingBundleReady: indexing.embeddingBundleReady,
    indexingRunStatus: indexing.run?.status ?? null,
    activationStatus: indexing.run?.activationStatus ?? null,
    retrievalProfileId: retrieval.retrievalProfileId,
    retrievalReady: retrieval.status?.readiness.ready ?? false,
    activeStage,
  });

  return (
    <div className="embedding-indexing-workspace">
      <PipelineHeader
        activeStage={activeStage}
        stageStatus={stageStatus}
        onStageChange={onStageChange}
        onRefresh={() => void pipeline.refreshCatalog()}
        refreshing={pipeline.refreshing}
      />

      <PipelineSummary
        selectedProfileId={embedding.selectedProfileId}
        selectedChunkBundleId={embedding.selectedChunkBundleId}
        embeddingBundleId={indexing.embeddingBundleId}
        indexingRunId={indexing.run?.runId ?? null}
        retrievalProfileId={retrieval.retrievalProfileId}
      />

      {activeStage === "embedding" ? (
        <div className="pipeline-stage-grid">
          <EmbeddingCatalogPanel
            profiles={embedding.profiles}
            loading={embedding.profilesLoading}
            error={embedding.profilesError}
            selectedProfileId={embedding.selectedProfileId}
            onSelectProfile={embedding.selectProfile}
          />
          <EmbeddingRunPanel
            selectedProfile={embedding.selectedProfile}
            chunkBundles={embedding.chunkBundles}
            chunkBundlesLoading={embedding.chunkBundlesLoading}
            chunkBundlesError={embedding.chunkBundlesError}
            selectedChunkBundleId={embedding.selectedChunkBundleId}
            onSelectChunkBundle={embedding.selectChunkBundle}
            run={embedding.run}
            polling={embedding.polling}
            launchBusy={embedding.launchBusy}
            launchError={embedding.launchError}
            onCreateRun={() => void embedding.createRun()}
          />
          <EmbeddingBundleInspector
            bundle={embedding.bundle}
            loading={embedding.bundleLoading}
            error={embedding.bundleError}
            chunksPage={embedding.bundleChunks}
            chunksLoading={embedding.bundleChunksLoading}
            validation={embedding.bundleValidation}
            readiness={embedding.bundleReadiness}
          />
        </div>
      ) : null}

      {activeStage === "indexing" ? (
        <div className="pipeline-stage-grid">
          <IndexingRunPanel
            embeddingBundleId={indexing.embeddingBundleId}
            embeddingBundleReady={indexing.embeddingBundleReady}
            bundleFirstEnabled={indexing.bundleFirstEnabled}
            run={indexing.run}
            polling={indexing.polling}
            launchBusy={indexing.launchBusy}
            launchError={indexing.launchError}
            onCreateRun={() => void indexing.createRun()}
          />
          <IndexingDocumentsTable
            documentsPage={indexing.documents}
            loading={indexing.documentsLoading}
            error={indexing.documentsError}
          />
          <IndexingErrorsPanel
            errorsPage={indexing.errors}
            loading={indexing.errorsLoading}
            error={indexing.errorsError}
          />
        </div>
      ) : null}

      {activeStage === "activation" ? (
        <div className="pipeline-stage-grid">
          <ActivationPanel
            run={activation.run}
            readiness={activation.readiness}
            lexicalFallbackPolicy={activation.lexicalFallbackPolicy}
            onPolicyChange={activation.setLexicalFallbackPolicy}
            activationBusy={activation.busy}
            activationError={activation.error}
            activationResult={activation.result}
            onActivate={() => void activation.activate()}
          />
          <PipelineHandoffPanel
            retrievalProfileId={retrieval.retrievalProfileId}
            onOpenRetrieval={() => onStageChange("retrieval")}
          />
        </div>
      ) : null}

      {activeStage === "retrieval" ? (
        <div className="pipeline-stage-grid">
          <RetrievalProfilesPanel
            profiles={retrieval.profiles}
            loading={retrieval.profilesLoading}
            error={retrieval.profilesError}
            selectedProfileId={retrieval.retrievalProfileId}
            onSelectProfile={retrieval.selectRetrievalProfile}
          />
          <RetrievalStatusPanel
            retrievalProfileId={retrieval.retrievalProfileId}
            status={retrieval.status}
            loading={retrieval.statusLoading}
            error={retrieval.statusError}
          />
          <RetrievalValidationPanel
            status={retrieval.status}
            validationBusy={retrieval.validationBusy}
            validationError={retrieval.validationError}
            validationResult={retrieval.validationResult}
            onValidate={() => void retrieval.validate()}
          />
        </div>
      ) : null}
    </div>
  );
}
