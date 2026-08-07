import { ArrowRight, CheckCircle2, CircleDashed } from "lucide-react";

type PipelineHandoffPanelProps = {
  retrievalProfileId: string | null;
  onOpenRetrieval: () => void;
};

// Bridges Activation into Retrieval. Activation returns a retrieval_profile_id;
// until then retrieval is genuinely unavailable and this panel says so instead
// of simulating a ready state.
export function PipelineHandoffPanel({
  retrievalProfileId,
  onOpenRetrieval,
}: PipelineHandoffPanelProps) {
  const handedOff = retrievalProfileId !== null;

  return (
    <section className="panel pipeline-handoff-panel" aria-label="Handoff a retrieval">
      <div className="panel-heading">
        <div>
          <h2>Handoff a retrieval</h2>
          <span>La activacion entrega el retrieval profile que habilita la ultima etapa.</span>
        </div>
      </div>
      <div className="pipeline-handoff-body">
        {handedOff ? (
          <div className="ui-note" role="status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <div className="ui-row-cell">
              <strong>Retrieval profile disponible</strong>
              <span>{retrievalProfileId}</span>
            </div>
          </div>
        ) : (
          <div className="ui-empty" role="status">
            <CircleDashed size={16} aria-hidden="true" />
            <span>Aun no hay retrieval profile. Completa la activacion para habilitar retrieval.</span>
          </div>
        )}
        <button
          type="button"
          className="secondary-button"
          onClick={onOpenRetrieval}
          disabled={!handedOff}
          title={
            handedOff
              ? "Ir a la etapa de retrieval"
              : "Disponible cuando la activacion devuelva un retrieval profile"
          }
        >
          <ArrowRight size={16} aria-hidden="true" />
          Ir a retrieval
        </button>
      </div>
    </section>
  );
}
