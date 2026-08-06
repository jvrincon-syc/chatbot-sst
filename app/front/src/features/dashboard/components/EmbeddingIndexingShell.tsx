import { ArrowRight, Boxes, Search, Waypoints, Workflow } from "lucide-react";
import type { EmbeddingIndexingStage } from "../dashboardTypes.js";

const EMBEDDING_INDEXING_STAGES: readonly {
  stage: EmbeddingIndexingStage;
  label: string;
  detail: string;
  icon: typeof Boxes;
}[] = [
  {
    stage: "embedding",
    label: "Embedding",
    detail: "Seleccion de profile y creacion de runs sobre chunk bundles.",
    icon: Boxes,
  },
  {
    stage: "indexing",
    label: "Indexing",
    detail: "Publicacion de embedding bundles al target compatible.",
    icon: Workflow,
  },
  {
    stage: "activation",
    label: "Activation",
    detail: "Activacion explicita del bundle indexado antes de retrieval.",
    icon: Waypoints,
  },
  {
    stage: "retrieval",
    label: "Retrieval",
    detail: "Validacion final del profile activo y su readiness.",
    icon: Search,
  },
];

export function EmbeddingIndexingShell({
  activeStage,
  onStageChange,
}: {
  activeStage: EmbeddingIndexingStage;
  onStageChange: (stage: EmbeddingIndexingStage) => void;
}) {
  const activeStageDefinition =
    EMBEDDING_INDEXING_STAGES.find((stage) => stage.stage === activeStage) ??
    EMBEDDING_INDEXING_STAGES[0];

  return (
    <section className="panel embedding-shell-panel" aria-label="Shell Embedding e Indexing">
      <div className="panel-heading">
        <div>
          <h2>Flujo bundle-first</h2>
          <span>
            La carcasa queda preparada para Embedding, Indexing, Activation y Retrieval antes
            de crear las features nuevas.
          </span>
        </div>
        <span className="embedding-shell-pill">Persistencia v2</span>
      </div>
      <div className="embedding-shell-body">
        <div className="embedding-stage-row" role="tablist" aria-label="Etapas bundle-first">
          {EMBEDDING_INDEXING_STAGES.map((stage, index) => {
            const Icon = stage.icon;
            const selected = stage.stage === activeStage;
            return (
              <div className="embedding-stage-fragment" key={stage.stage}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  className={selected ? "embedding-stage-button active" : "embedding-stage-button"}
                  onClick={() => onStageChange(stage.stage)}
                >
                  <Icon size={16} />
                  <span>{stage.label}</span>
                </button>
                {index < EMBEDDING_INDEXING_STAGES.length - 1 ? <ArrowRight size={14} /> : null}
              </div>
            );
          })}
        </div>

        <div className="embedding-shell-grid">
          <article className="embedding-shell-card">
            <span className="embedding-shell-eyebrow">Etapa activa</span>
            <strong>{activeStageDefinition.label}</strong>
            <p>{activeStageDefinition.detail}</p>
          </article>
          <article className="embedding-shell-card">
            <span className="embedding-shell-eyebrow">Que ya quedo listo</span>
            <ul>
              <li>Vista nueva registrada en AppView y en la navegacion compartida.</li>
              <li>Persistencia v2 con estado minimo de embeddingIndexing.</li>
              <li>Review e inventory siguen usando su seleccion actual sin cambios.</li>
            </ul>
          </article>
        </div>
      </div>
    </section>
  );
}
