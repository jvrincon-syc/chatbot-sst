import { type FormEvent } from "react";
import { Boxes, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import { VariantMatrixTable } from "./VariantMatrixTable.js";
import {
  useVariantMatrixWorkspace,
  type VariantsState,
} from "./useVariantMatrixWorkspace.js";

// Composición pura del workspace de variantes: estado en useVariantMatrixWorkspace,
// presentación de la rejilla en VariantMatrixTable. Aquí solo layout, notice, el
// formulario de slug y el listado de variantes existentes.
export function VariantMatrixWorkspace() {
  const workspace = useVariantMatrixWorkspace();
  const matrixLoading = workspace.matrix.status === "loading";

  // Motivo visible del bloqueo del envío: nunca se deshabilita sin explicar por qué.
  const submitReason = !workspace.selectedCell
    ? "Selecciona una celda construible de la matriz para crear una variante."
    : workspace.slug.trim().length === 0
      ? "Escribe un slug para la variante."
      : null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace.canSubmit) {
      return;
    }
    void workspace.submit();
  }

  return (
    <main className="workspace operator-workspace platform-workspace">
      <header className="topbar">
        <div>
          <h1>Matriz de variantes</h1>
          <p>Cada variante deriva de una celda reconfirmada de la configuración vigente.</p>
        </div>
        <div className="topbar-actions">
          <button
            className="ghost-button"
            type="button"
            onClick={workspace.refetchMatrix}
            disabled={!workspace.projectId || matrixLoading}
          >
            {matrixLoading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Actualizar
          </button>
        </div>
      </header>

      {workspace.notice ? (
        <DashboardNotice tone={workspace.notice.tone} message={workspace.notice.message} />
      ) : null}

      <section className="variant-grid">
        <section className="panel" aria-label="Matriz de recetas">
          <div className="panel-heading">
            <div>
              <h2>Celdas de receta</h2>
              <span>Elige una celda construible; el target físico ya vive dentro de la celda.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <VariantMatrixTable
              state={workspace.matrix}
              selectedCellId={workspace.selectedCellId}
              onSelectCell={workspace.selectCell}
              onRetry={workspace.refetchMatrix}
            />
          </div>
        </section>

        <aside className="variant-aside">
          <section className="panel" aria-label="Nueva variante">
            <div className="panel-heading">
              <div>
                <h2>Nueva variante</h2>
                <span>Solo se envían la celda seleccionada y el slug.</span>
              </div>
            </div>
            <div className="ui-panel-body">
              {workspace.selectedCell ? (
                <p className="ui-note">
                  <Sparkles size={16} />
                  <span>
                    Celda <strong>{workspace.selectedCell.target_binding_key}</strong> · Config v
                    {workspace.selectedCell.configuration_version}
                  </span>
                </p>
              ) : null}
              <form className="platform-create-form" onSubmit={handleSubmit}>
                <div className="ui-field">
                  <label htmlFor="variant-slug">Slug de la variante</label>
                  <input
                    id="variant-slug"
                    value={workspace.slug}
                    placeholder="mi-variante"
                    autoComplete="off"
                    onChange={(event) => workspace.setSlug(event.target.value)}
                  />
                  <span className="ui-field-note">Identidad legible de la variante.</span>
                </div>
                <div className="ui-actions">
                  <button className="primary-button" type="submit" disabled={!workspace.canSubmit}>
                    {workspace.submitting ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Sparkles size={16} />
                    )}
                    Crear variante
                  </button>
                </div>
                {submitReason ? (
                  <span className="ui-field-note">{submitReason}</span>
                ) : null}
              </form>
            </div>
          </section>

          <ExistingVariants state={workspace.variants} />
        </aside>
      </section>
    </main>
  );
}

function ExistingVariants({ state }: { state: VariantsState }) {
  return (
    <section className="panel" aria-label="Variantes existentes">
      <div className="panel-heading">
        <div>
          <h2>Variantes existentes</h2>
          <span>Recetas ya materializadas en este proyecto.</span>
        </div>
      </div>
      <div className="ui-panel-body">
        {state.status === "idle" ? (
          <div className="ui-empty compact">
            <Boxes size={22} />
            <span>Selecciona un proyecto para ver sus variantes.</span>
          </div>
        ) : state.status === "loading" ? (
          <div className="ui-empty compact">
            <Loader2 className="spin" size={20} />
            <span>Cargando variantes...</span>
          </div>
        ) : state.status === "error" ? (
          <p className="ui-field-note error" role="alert">
            {state.message}
          </p>
        ) : state.status === "empty" ? (
          <div className="ui-empty compact">
            <Boxes size={22} />
            <span>Aún no hay variantes. Confirma una celda de la matriz para crear la primera.</span>
          </div>
        ) : (
          <ul className="ui-list" aria-label="Lista de variantes">
            {state.variants.map((variant) => (
              <li key={variant.rag_variant_id}>
                <div className="ui-list-card">
                  <strong>{variant.rag_variant_id}</strong>
                  <small>
                    Estado: {variant.state} · {variant.processing_profile_id} ·{" "}
                    {variant.chunking_profile_id} · {variant.embedding_profile_id}
                  </small>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
