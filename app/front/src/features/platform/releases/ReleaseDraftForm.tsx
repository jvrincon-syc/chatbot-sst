import { Loader2, PackagePlus } from "lucide-react";
import type { CorpusSnapshot, Variant } from "../platformTypes.js";

// Formulario del draft: elige variante RAG, snapshot de corpus y `target_binding_key`
// (clave LÓGICA, read-only desde la configuración; nunca un target físico). El body
// resultante es EXACTO: {corpus_snapshot_id, rag_variant_id, target_binding_key}.
export function ReleaseDraftForm({
  variants,
  snapshots,
  bindingKeys,
  variantId,
  snapshotId,
  bindingKey,
  creating,
  canCreate,
  onVariantChange,
  onSnapshotChange,
  onBindingKeyChange,
  onCreate,
}: {
  variants: Variant[];
  snapshots: CorpusSnapshot[];
  bindingKeys: string[];
  variantId: string | null;
  snapshotId: string | null;
  bindingKey: string | null;
  creating: boolean;
  canCreate: boolean;
  onVariantChange: (value: string) => void;
  onSnapshotChange: (value: string) => void;
  onBindingKeyChange: (value: string) => void;
  onCreate: () => void;
}) {
  const missing: string[] = [];
  if (variants.length === 0) missing.push("una variante RAG (créala en la matriz)");
  if (snapshots.length === 0) missing.push("un snapshot de corpus");
  if (bindingKeys.length === 0) missing.push("un target binding en la configuración");

  const disabledReason = creating
    ? "Creando draft..."
    : missing.length > 0
      ? `Falta ${missing.join(", ")}.`
      : !variantId
        ? "Selecciona una variante."
        : !snapshotId
          ? "Selecciona un snapshot."
          : !bindingKey
            ? "Selecciona un target binding key."
            : null;

  return (
    <form
      className="release-draft-form"
      onSubmit={(event) => {
        event.preventDefault();
        onCreate();
      }}
    >
      <div className="ui-field">
        <label htmlFor="release-variant">Variante RAG</label>
        <select
          id="release-variant"
          value={variantId ?? ""}
          disabled={variants.length === 0}
          onChange={(event) => onVariantChange(event.target.value)}
        >
          {variants.length === 0 ? <option value="">Sin variantes disponibles</option> : null}
          {variants.map((variant) => (
            <option key={variant.rag_variant_id} value={variant.rag_variant_id}>
              {variant.rag_variant_id} · {variant.state}
            </option>
          ))}
        </select>
      </div>

      <div className="ui-field">
        <label htmlFor="release-snapshot">Snapshot de corpus</label>
        <select
          id="release-snapshot"
          value={snapshotId ?? ""}
          disabled={snapshots.length === 0}
          onChange={(event) => onSnapshotChange(event.target.value)}
        >
          {snapshots.length === 0 ? <option value="">Sin snapshots disponibles</option> : null}
          {snapshots.map((snapshot) => (
            <option key={snapshot.corpus_snapshot_id} value={snapshot.corpus_snapshot_id}>
              {snapshot.corpus_snapshot_id} · {snapshot.document_count} doc(s)
            </option>
          ))}
        </select>
      </div>

      <div className="ui-field">
        <label htmlFor="release-binding">Target binding key (lógico)</label>
        <select
          id="release-binding"
          value={bindingKey ?? ""}
          disabled={bindingKeys.length === 0}
          onChange={(event) => onBindingKeyChange(event.target.value)}
        >
          {bindingKeys.length === 0 ? <option value="">Sin bindings configurados</option> : null}
          {bindingKeys.map((key) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </select>
      </div>

      <div className="platform-actions">
        <button
          className="primary-button"
          type="submit"
          disabled={!canCreate}
          title={disabledReason ?? undefined}
        >
          {creating ? <Loader2 className="spin" size={16} /> : <PackagePlus size={16} />}
          Crear draft
        </button>
        {disabledReason ? (
          <span className="ui-hint" role="note">
            {disabledReason}
          </span>
        ) : null}
      </div>
    </form>
  );
}
