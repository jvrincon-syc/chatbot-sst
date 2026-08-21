import { type FormEvent } from "react";
import { AlertTriangle, Loader2, Wand2 } from "lucide-react";
import type { ProjectNormalizeReport, Variant } from "../platformTypes.js";
import type { VariantsState } from "./useDocumentIntakeWorkspace.js";

// Panel 3: normalización por variante. La normalización va SIEMPRE por
// rag_variant_id (invariante D8). `force` re-normaliza aunque el hash no cambie:
// se etiqueta con ese efecto para no confundirlo con reintentar/reprocesar.
export function NormalizationPanel({
  variants,
  selectedVariantId,
  selectedCount,
  force,
  normalizing,
  canNormalize,
  report,
  onSelectVariant,
  onToggleForce,
  onNormalize,
}: {
  variants: VariantsState;
  selectedVariantId: string | null;
  selectedCount: number;
  force: boolean;
  normalizing: boolean;
  canNormalize: boolean;
  report: ProjectNormalizeReport | null;
  onSelectVariant: (variantId: string) => void;
  onToggleForce: () => void;
  onNormalize: () => Promise<boolean>;
}) {
  // Motivo visible del bloqueo: nunca se deshabilita sin explicar por qué.
  const reason =
    selectedVariantId === null
      ? "Elige una variante para normalizar."
      : selectedCount === 0
        ? "Selecciona al menos una revisión en la tabla."
        : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canNormalize) {
      return;
    }
    void onNormalize();
  }

  return (
    <section className="panel" aria-label="Normalizar documentos">
      <div className="panel-heading">
        <div>
          <h2>Normalizar</h2>
          <span>Normaliza las revisiones seleccionadas bajo una variante reconfirmada.</span>
        </div>
      </div>
      <div className="ui-panel-body">
        <form className="platform-create-form" onSubmit={handleSubmit}>
          <div className="ui-field">
            <label htmlFor="normalize-variant">Variante (rag_variant_id)</label>
            <VariantSelect
              variants={variants}
              selectedVariantId={selectedVariantId}
              onSelectVariant={onSelectVariant}
            />
            <span className="ui-field-note">
              La normalización opera por variante, nunca por un perfil de procesamiento libre.
            </span>
          </div>

          <div className="ui-field">
            <label className="ui-toggle-row" htmlFor="normalize-force">
              <input
                id="normalize-force"
                type="checkbox"
                checked={force}
                onChange={onToggleForce}
              />
              <span>Forzar re-normalización</span>
            </label>
            <span className="ui-field-note">
              Vuelve a normalizar aunque el hash no haya cambiado (no es un reintento).
            </span>
          </div>

          <div className="ui-actions">
            <button className="primary-button" type="submit" disabled={!canNormalize}>
              {normalizing ? <Loader2 className="spin" size={16} /> : <Wand2 size={16} />}
              Normalizar {selectedCount > 0 ? `(${selectedCount})` : ""}
            </button>
          </div>
          {reason ? <span className="ui-field-note">{reason}</span> : null}
        </form>

        {report ? <NormalizeReport report={report} /> : null}
      </div>
    </section>
  );
}

function VariantSelect({
  variants,
  selectedVariantId,
  onSelectVariant,
}: {
  variants: VariantsState;
  selectedVariantId: string | null;
  onSelectVariant: (variantId: string) => void;
}) {
  if (variants.status === "loading") {
    return <p className="ui-field-note">Cargando variantes...</p>;
  }
  if (variants.status === "error") {
    return (
      <p className="ui-field-note error" role="alert">
        {variants.message}
      </p>
    );
  }
  if (variants.status === "idle") {
    return <p className="ui-field-note">Selecciona un proyecto para ver sus variantes.</p>;
  }
  if (variants.status === "empty") {
    return (
      <p className="ui-field-note">
        Este proyecto aún no tiene variantes. Crea una en la matriz de variantes.
      </p>
    );
  }
  return (
    <select
      id="normalize-variant"
      value={selectedVariantId ?? ""}
      onChange={(event) => onSelectVariant(event.target.value)}
    >
      <option value="" disabled>
        Elige una variante...
      </option>
      {variants.variants.map((variant: Variant) => (
        <option key={variant.rag_variant_id} value={variant.rag_variant_id}>
          {variant.rag_variant_id} · {variant.state}
        </option>
      ))}
    </select>
  );
}

function NormalizeReport({ report }: { report: ProjectNormalizeReport }) {
  const needsReview = report.needs_review > 0;
  return (
    <div className="platform-report" aria-label="Reporte de normalización">
      <p className="ui-note">
        <span>
          Variante <strong>{report.rag_variant_id}</strong>
        </span>
      </p>
      <ul className="ui-status-row">
        <li className="ui-status-chip success">Procesadas: {report.processed}</li>
        {/* needs_review nunca se oculta tras el éxito: se resalta como atención. */}
        <li className={`ui-status-chip ${needsReview ? "warning" : "neutral"}`}>
          {needsReview ? (
            <>
              <AlertTriangle size={12} /> Requieren revisión: {report.needs_review}
            </>
          ) : (
            `Requieren revisión: ${report.needs_review}`
          )}
        </li>
        <li className="ui-status-chip neutral">Omitidas: {report.skipped}</li>
        <li className={`ui-status-chip ${report.failed > 0 ? "danger" : "neutral"}`}>
          Fallidas: {report.failed}
        </li>
      </ul>
    </div>
  );
}
