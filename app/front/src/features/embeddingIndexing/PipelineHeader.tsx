import { RefreshCw } from "lucide-react";
import { PipelineStepper, type PipelineStageStatus } from "./PipelineStepper.js";
import type { PipelineStage } from "./shared/pipelineFlow.js";
import type { EmbeddingIndexingStage } from "../dashboard/dashboardTypes.js";

type PipelineHeaderProps = {
  activeStage: EmbeddingIndexingStage;
  stageStatus: Record<PipelineStage, PipelineStageStatus>;
  onStageChange: (stage: EmbeddingIndexingStage) => void;
  onRefresh: () => void;
  refreshing: boolean;
};

// Header for the unified workspace: title, the 4-stage stepper, and a manual
// refresh of the catalog-level reads.
export function PipelineHeader({
  activeStage,
  stageStatus,
  onStageChange,
  onRefresh,
  refreshing,
}: PipelineHeaderProps) {
  return (
    <section className="panel pipeline-header-panel" aria-label="Encabezado del pipeline">
      <div className="panel-heading">
        <div>
          <h2>Flujo bundle-first</h2>
          <span>Embedding, Indexing, Activation y Retrieval como etapas explicitas.</span>
        </div>
        <button
          type="button"
          className="ghost-button"
          onClick={onRefresh}
          disabled={refreshing}
          title="Recargar catalogos de embedding e indexing"
        >
          <RefreshCw size={16} aria-hidden="true" />
          Actualizar
        </button>
      </div>
      <div className="pipeline-header-body">
        <PipelineStepper
          activeStage={activeStage}
          stageStatus={stageStatus}
          onStageChange={onStageChange}
        />
      </div>
    </section>
  );
}
