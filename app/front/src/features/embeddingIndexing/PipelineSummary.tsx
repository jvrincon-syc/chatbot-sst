type PipelineSummaryProps = {
  selectedProfileId: string | null;
  selectedChunkBundleId: string | null;
  embeddingBundleId: string | null;
  indexingRunId: string | null;
  retrievalProfileId: string | null;
};

// Compact, read-only snapshot of the ids flowing through the pipeline. It shows
// working identifiers only; never vectors, absolute paths, or raw payloads.
export function PipelineSummary({
  selectedProfileId,
  selectedChunkBundleId,
  embeddingBundleId,
  indexingRunId,
  retrievalProfileId,
}: PipelineSummaryProps) {
  return (
    <section className="panel pipeline-summary-panel" aria-label="Resumen del pipeline">
      <div className="panel-heading">
        <div>
          <h2>Estado del pipeline</h2>
          <span>Identificadores en curso a traves de las cuatro etapas.</span>
        </div>
      </div>
      <dl className="pipeline-summary-grid">
        <SummaryItem label="Perfil embedding" value={selectedProfileId} />
        <SummaryItem label="Chunk bundle" value={selectedChunkBundleId} />
        <SummaryItem label="Embedding bundle" value={embeddingBundleId} />
        <SummaryItem label="Indexing run" value={indexingRunId} />
        <SummaryItem label="Retrieval profile" value={retrievalProfileId} />
      </dl>
    </section>
  );
}

function SummaryItem({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={value ? undefined : "muted"}>{value ?? "Sin asignar"}</dd>
    </div>
  );
}
