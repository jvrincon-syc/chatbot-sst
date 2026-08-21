import { AlertCircle, Loader2, RefreshCw, Rocket } from "lucide-react";
import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import { BuildReport } from "./BuildReport.js";
import { ReleaseDraftForm } from "./ReleaseDraftForm.js";
import { ReleaseHistory } from "./ReleaseHistory.js";
import { ReleaseLifecycle } from "./ReleaseLifecycle.js";
import { useRagReleaseWorkspace } from "./useRagReleaseWorkspace.js";

// Composición pura del release lifecycle workspace: estado en el hook, presentación
// en los subcomponentes. Aquí solo layout, topbar, notice y estados globales.
export function RagReleaseWorkspace() {
  const workspace = useRagReleaseWorkspace();
  const loading = workspace.load.status === "loading";

  return (
    <main className="workspace operator-workspace platform-workspace">
      <header className="topbar">
        <div>
          <h1>Ciclo de vida de releases</h1>
          <p>
            De un draft (variante + snapshot + binding lógico) a build, validación,
            publicación y retiro. El backend resuelve la receta; React nunca orquesta
            chunking/embedding/indexing legacy.
          </p>
        </div>
        <div className="topbar-actions">
          <button
            className="ghost-button"
            type="button"
            onClick={workspace.refresh}
            disabled={!workspace.projectId || loading}
          >
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Actualizar
          </button>
        </div>
      </header>

      {workspace.notice ? (
        <DashboardNotice tone={workspace.notice.tone} message={workspace.notice.message} />
      ) : null}

      <RagReleaseBody workspace={workspace} />
    </main>
  );
}

function RagReleaseBody({ workspace }: { workspace: ReturnType<typeof useRagReleaseWorkspace> }) {
  const { load } = workspace;

  if (load.status === "no-project") {
    return (
      <section className="panel">
        <div className="ui-empty">
          <Rocket size={24} />
          <span>Selecciona un proyecto para gestionar sus releases.</span>
        </div>
      </section>
    );
  }

  if (load.status === "loading") {
    return (
      <section className="panel">
        <div className="ui-empty">
          <Loader2 className="spin" size={22} />
          <span>Cargando releases y opciones del draft...</span>
        </div>
      </section>
    );
  }

  if (load.status === "error") {
    return (
      <section className="panel">
        <div className="ui-empty">
          <AlertCircle size={24} />
          <span role="alert">{load.message}</span>
          <button className="secondary-button" type="button" onClick={workspace.refresh}>
            <RefreshCw size={16} />
            Reintentar
          </button>
        </div>
      </section>
    );
  }

  const { data } = load;
  return (
    <section className="release-grid">
      <div className="release-aside">
        <section className="panel" aria-label="Nuevo draft de release">
          <div className="panel-heading">
            <div>
              <h2>Nuevo draft</h2>
              <span>Congela variante, snapshot y binding lógico en una release reproducible.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <ReleaseDraftForm
              variants={data.variants}
              snapshots={data.snapshots}
              bindingKeys={data.bindingKeys}
              variantId={workspace.draftVariantId}
              snapshotId={workspace.draftSnapshotId}
              bindingKey={workspace.draftBindingKey}
              creating={workspace.creating}
              canCreate={workspace.canCreateDraft}
              onVariantChange={workspace.setDraftVariantId}
              onSnapshotChange={workspace.setDraftSnapshotId}
              onBindingKeyChange={workspace.setDraftBindingKey}
              onCreate={workspace.createDraft}
            />
          </div>
        </section>

        <section className="panel" aria-label="Historial de releases">
          <div className="panel-heading">
            <div>
              <h2>Historial</h2>
              <span>Releases del proyecto; la seleccionada se rehidrata tras un refresh.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <ReleaseHistory
              releases={data.releases}
              selectedReleaseId={workspace.selectedReleaseId}
              onSelect={workspace.selectRelease}
            />
          </div>
        </section>
      </div>

      <div className="release-main">
        <section className="panel" aria-label="Ciclo de vida de la release">
          <div className="panel-heading">
            <div>
              <h2>Lifecycle</h2>
              <span>Solo se ofrecen las transiciones válidas para el estado actual.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <ReleaseLifecycle
              release={workspace.selectedRelease}
              busyAction={workspace.busyAction}
              onBuild={workspace.build}
              onValidate={workspace.validate}
              onPublish={workspace.publish}
              onRetire={workspace.retire}
            />
          </div>
        </section>

        <section className="panel" aria-label="Informe de build">
          <div className="panel-heading">
            <div>
              <h2>Informe de build</h2>
              <span>Resultado del último build de la release seleccionada.</span>
            </div>
          </div>
          <div className="ui-panel-body">
            <BuildReport state={workspace.buildReport} />
          </div>
        </section>
      </div>
    </section>
  );
}
