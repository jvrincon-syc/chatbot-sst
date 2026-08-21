import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createProject as apiCreateProject,
  getConfiguration,
  listProjects,
  updateConfiguration as apiUpdateConfiguration,
  updateProject as apiUpdateProject,
} from "../platformApi.js";
import { usePlatformPreferences } from "../hooks/usePlatformPreferences.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
import type {
  CreateProjectRequest,
  Project,
  ProjectConfiguration,
  UpdateProjectConfigurationRequest,
} from "../platformTypes.js";

// Estado de servidor + acciones del workspace de proyectos. Los componentes
// reciben datos ya resueltos y callbacks; no hacen fetch ni traducen errores.
export type ProjectWorkspaceNotice =
  | { tone: "info" | "success" | "warning" | "danger"; message: string }
  | null;

// Traducción fail-closed de errores de transporte a copia de UI. Nunca asume
// éxito: cada acción que falla deja un notice de peso (danger) con qué pasó.
function messageFromError(error: unknown): string {
  const mapped = mapPipelineError(error);
  if (mapped.status === 403) {
    return "No autorizado para esta operación.";
  }
  if (mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED") {
    return "Problema de configuración del servidor de auth, no de tu sesión.";
  }
  // 422 y el resto: se surfacea el mensaje de validación tal cual lo envía el
  // backend (campo concreto), sin ocultarlo tras un genérico.
  return mapped.message;
}

export function useProjectWorkspace() {
  // scope = null: Task 7 solo gestiona la selección de proyecto. La reconciliación
  // full-scope (variante/snapshot/release) pertenece a un provider posterior.
  const { preferences, setSelectedProject } = usePlatformPreferences(null);
  const selectedProjectId = preferences.selectedProjectId;

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [configuration, setConfiguration] = useState<ProjectConfiguration | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  const [notice, setNotice] = useState<ProjectWorkspaceNotice>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [renamingProject, setRenamingProject] = useState(false);
  const [savingConfiguration, setSavingConfiguration] = useState(false);

  // Si el proyecto persistido ya no está en la lista viva, se trata como
  // "ninguno seleccionado": no se pinta detalle ni se pide configuración.
  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );
  const activeProjectId = selectedProject?.project_id ?? null;

  const loadProjects = useCallback(async (signal?: AbortSignal) => {
    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const page = await listProjects(undefined, { signal });
      if (signal?.aborted) {
        return;
      }
      // Trust boundary: el contrato garantiza `items`, pero se valida para no
      // romper el render ante una respuesta malformada.
      setProjects(Array.isArray(page.items) ? page.items : []);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      const message = messageFromError(error);
      setProjectsError(message);
      setNotice({ tone: "danger", message });
    } finally {
      if (!signal?.aborted) {
        setProjectsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadProjects(controller.signal);
    return () => controller.abort();
  }, [loadProjects]);

  // Carga de configuración del proyecto seleccionado. Se cancela al cambiar de
  // proyecto (o al desmontar) para evitar condiciones de carrera entre detalles.
  useEffect(() => {
    if (!activeProjectId) {
      setConfiguration(null);
      setConfigError(null);
      setConfigLoading(false);
      return;
    }
    const controller = new AbortController();
    setConfigLoading(true);
    setConfigError(null);
    void (async () => {
      try {
        const config = await getConfiguration(activeProjectId, { signal: controller.signal });
        if (controller.signal.aborted) {
          return;
        }
        setConfiguration(config);
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        const message = messageFromError(error);
        setConfigError(message);
        setConfiguration(null);
        setNotice({ tone: "danger", message });
      } finally {
        if (!controller.signal.aborted) {
          setConfigLoading(false);
        }
      }
    })();
    return () => controller.abort();
  }, [activeProjectId]);

  const selectProject = useCallback(
    (projectId: string) => {
      setNotice(null);
      setSelectedProject(projectId);
    },
    [setSelectedProject],
  );

  const createProject = useCallback(
    async (body: CreateProjectRequest): Promise<boolean> => {
      setCreatingProject(true);
      setNotice(null);
      try {
        const project = await apiCreateProject(body);
        setProjects((current) => [
          project,
          ...current.filter((item) => item.project_id !== project.project_id),
        ]);
        setSelectedProject(project.project_id);
        setNotice({ tone: "success", message: `Proyecto "${project.display_name}" creado.` });
        return true;
      } catch (error) {
        setNotice({ tone: "danger", message: messageFromError(error) });
        return false;
      } finally {
        setCreatingProject(false);
      }
    },
    [setSelectedProject],
  );

  const renameProject = useCallback(
    async (displayName: string): Promise<boolean> => {
      if (!activeProjectId) {
        return false;
      }
      setRenamingProject(true);
      setNotice(null);
      try {
        const updated = await apiUpdateProject(activeProjectId, { display_name: displayName });
        setProjects((current) =>
          current.map((item) => (item.project_id === updated.project_id ? updated : item)),
        );
        setNotice({ tone: "success", message: "Nombre del proyecto actualizado." });
        return true;
      } catch (error) {
        setNotice({ tone: "danger", message: messageFromError(error) });
        return false;
      } finally {
        setRenamingProject(false);
      }
    },
    [activeProjectId],
  );

  const saveConfigurationVersion = useCallback(
    async (body: UpdateProjectConfigurationRequest): Promise<boolean> => {
      if (!activeProjectId) {
        return false;
      }
      setSavingConfiguration(true);
      setNotice(null);
      try {
        const next = await apiUpdateConfiguration(activeProjectId, body);
        setConfiguration(next);
        setNotice({ tone: "success", message: `Configuración v${next.version} guardada.` });
        return true;
      } catch (error) {
        setNotice({ tone: "danger", message: messageFromError(error) });
        return false;
      } finally {
        setSavingConfiguration(false);
      }
    },
    [activeProjectId],
  );

  const refresh = useCallback(() => {
    void loadProjects();
  }, [loadProjects]);

  return {
    projects,
    projectsLoading,
    projectsError,
    selectedProjectId,
    selectedProject,
    configuration,
    configLoading,
    configError,
    notice,
    creatingProject,
    renamingProject,
    savingConfiguration,
    selectProject,
    createProject,
    renameProject,
    saveConfigurationVersion,
    refresh,
  };
}
