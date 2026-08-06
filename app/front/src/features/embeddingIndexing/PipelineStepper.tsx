import { ArrowRight, Boxes, Search, Waypoints, Workflow } from "lucide-react";
import { pipelineStageOrder, type PipelineStage } from "./shared/pipelineFlow.js";
import type { EmbeddingIndexingStage } from "../dashboard/dashboardTypes.js";

export type PipelineStageStatus = "pending" | "active" | "done" | "blocked";

type StageMeta = {
  stage: PipelineStage;
  label: string;
  icon: typeof Boxes;
};

const STAGE_META: Record<PipelineStage, StageMeta> = {
  embedding: { stage: "embedding", label: "Embedding", icon: Boxes },
  indexing: { stage: "indexing", label: "Indexing", icon: Workflow },
  activation: { stage: "activation", label: "Activation", icon: Waypoints },
  retrieval: { stage: "retrieval", label: "Retrieval", icon: Search },
};

type PipelineStepperProps = {
  activeStage: EmbeddingIndexingStage;
  stageStatus: Record<PipelineStage, PipelineStageStatus>;
  onStageChange: (stage: EmbeddingIndexingStage) => void;
};

// Four-stage stepper. Activation is a distinct, selectable stage between Indexing
// and Retrieval. Each stage carries a text status, not color alone.
export function PipelineStepper({
  activeStage,
  stageStatus,
  onStageChange,
}: PipelineStepperProps) {
  const stages = pipelineStageOrder();

  return (
    <div className="pipeline-stepper" role="tablist" aria-label="Etapas del pipeline bundle-first">
      {stages.map((stage, index) => {
        const meta = STAGE_META[stage];
        const Icon = meta.icon;
        const selected = stage === activeStage;
        const status = stageStatus[stage];
        return (
          <div className="pipeline-step-fragment" key={stage}>
            <button
              type="button"
              role="tab"
              aria-selected={selected}
              className={selected ? "pipeline-step active" : "pipeline-step"}
              data-status={status}
              onClick={() => onStageChange(stage)}
            >
              <span className="pipeline-step-index" aria-hidden="true">
                {index + 1}
              </span>
              <Icon size={16} aria-hidden="true" />
              <span className="pipeline-step-label">{meta.label}</span>
              <span className="pipeline-step-status">{stageStatusLabel(status)}</span>
            </button>
            {index < stages.length - 1 ? (
              <ArrowRight size={14} aria-hidden="true" className="pipeline-step-arrow" />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function stageStatusLabel(status: PipelineStageStatus): string {
  if (status === "active") return "En curso";
  if (status === "done") return "Listo";
  if (status === "blocked") return "Bloqueado";
  return "Pendiente";
}
