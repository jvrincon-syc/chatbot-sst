import { FolderOpen, Loader2, RefreshCw } from "lucide-react";
import { DashboardNotice } from "../../dashboard/components/DashboardChrome.js";
import { ProjectConfigurationForm } from "./ProjectConfigurationForm.js";
import { ProjectList } from "./ProjectList.js";
import { useProjectWorkspace } from "./useProjectWorkspace.js";

// Composición pura del workspace de proyectos: estado en useProjectWorkspace,
// presentación en ProjectList / ProjectConfigurationForm. Solo orquesta layout,
// notice y los estados loading/empty del detalle.
export function ProjectWorkspace() {
  const workspace = useProjectWorkspace();

  return (
    <main className="workspace operator-workspace platform-workspace">
      <header className="topbar">
        <div>
          <h1>RAG Platform</h1>
          <p>Administración de proyectos y su configuración versionada.</p>
        </div>
        <div className="topbar-actions">
          <button
            className="ghost-button"
            type="button"
            onClick={workspace.refresh}
            disabled={workspace.projectsLoading}
          >
            {workspace.projectsLoading ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <RefreshCw size={16} />
            )}
            Actualizar
          </button>
        </div>
      </header>

      {workspace.notice ? (
        <DashboardNotice tone={workspace.notice.tone} message={workspace.notice.message} />
      ) : null}

      <section className="platform-grid">
        <ProjectList
          projects={workspace.projects}
          selectedProjectId={workspace.selectedProjectId}
          loading={workspace.projectsLoading}
          error={workspace.projectsError}
          creating={workspace.creatingProject}
          onSelect={workspace.selectProject}
          onCreate={workspace.createProject}
          onRefresh={workspace.refresh}
        />

        <div className="platform-detail">
          {workspace.selectedProject && workspace.configuration ? (
            <ProjectConfigurationForm
              key={`${workspace.selectedProject.project_id}:${workspace.configuration.version}`}
              project={workspace.selectedProject}
              configuration={workspace.configuration}
              renaming={workspace.renamingProject}
              saving={workspace.savingConfiguration}
              onRename={workspace.renameProject}
              onSaveConfiguration={workspace.saveConfigurationVersion}
            />
          ) : (
            <section className="panel" aria-label="Detalle del proyecto">
              <div className="panel-heading">
                <div>
                  <h2>Configuración</h2>
                  <span>El detalle aparece al seleccionar un proyecto.</span>
                </div>
              </div>
              <div className="ui-empty">
                {workspace.configLoading ? (
                  <>
                    <Loader2 className="spin" size={22} />
                    <span>Cargando configuración...</span>
                  </>
                ) : workspace.configError ? (
                  <span role="alert">{workspace.configError}</span>
                ) : (
                  <>
                    <FolderOpen size={24} />
                    <span>Selecciona un proyecto de la lista para ver y versionar su configuración.</span>
                  </>
                )}
              </div>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
