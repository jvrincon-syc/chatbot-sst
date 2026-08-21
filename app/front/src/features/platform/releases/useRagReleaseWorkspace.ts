import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  buildRelease,
  createReleaseDraft,
  getConfiguration,
  getRelease,
  listAllCorpusSnapshots,
  listAllReleases,
  listAllVariants,
  publishRelease,
  retireRelease,
  validateRelease,
} from "../platformApi.js";
import { usePlatformPreferences } from "../hooks/usePlatformPreferences.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
import type { CorpusSnapshot, Release, ReleaseBuildReport, Variant } from "../platformTypes.js";
import { useIdempotentReleaseAction } from "./useIdempotentReleaseAction.js";

// Estado de servidor + acciones del workspace de release lifecycle. Los componentes
// reciben datos ya resueltos y callbacks; no hacen fetch ni traducen errores ni
// conocen la máquina de estados (solo transiciones válidas → botones contextuales).
// D9: la ÚNICA operación de build es `POST /releases/{id}/build`; React nunca llama
// endpoints legacy de chunking/embedding/indexing.

export type ReleaseWorkspaceData = {
  releases: Release[];
  variants: Variant[];
  snapshots: CorpusSnapshot[];
  bindingKeys: string[];
};

export type ReleaseLoadState =
  | { status: "no-project" }
  | { status: "loading" }
  | { status: "ready"; data: ReleaseWorkspaceData }
  | { status: "error"; message: string };

export type BuildReportState =
  | { status: "idle" }
  | { status: "success"; report: ReleaseBuildReport };

export type ReleaseWorkspaceNotice =
  | { tone: "info" | "success" | "warning" | "danger"; message: string }
  | null;

// Traducción fail-closed de errores de transporte a copia de UI. Nunca oculta un
// bloqueo tras un genérico ni tras un éxito aparente.
function messageFromError(error: unknown): string {
  const mapped = mapPipelineError(error);
  if (mapped.status === 403) {
    return "No autorizado para esta operación.";
  }
  if (mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED") {
    return "Problema de configuración del servidor de auth, no de tu sesión.";
  }
  if (mapped.code === "IDEMPOTENCY_KEY_CONFLICT") {
    return "Conflicto de clave de idempotencia: la operación ya está en curso o se envió con otra intención. No se reintenta sola; confirma o abandónala explícitamente.";
  }
  if (mapped.code === "RELEASE_BUILD_TOO_LARGE") {
    return "El build supera el límite permitido. Reduce el snapshot de corpus (menos revisiones) e inténtalo de nuevo.";
  }
  if (mapped.code === "IDEMPOTENT_OPERATION_FAILED") {
    return "La operación idempotente falló de forma definitiva. Requiere un intento nuevo y explícito.";
  }
  // 422 (validación) y el resto: mensaje del backend tal cual, sin ocultarlo.
  return mapped.message;
}

export function useRagReleaseWorkspace() {
  // scope = null: solo lee la selección de proyecto vigente y persiste la release
  // elegida (D6: solo IDs de navegación).
  const { preferences, setSelectedRagRelease } = usePlatformPreferences(null);
  const projectId = preferences.selectedProjectId;
  const selectedReleaseId = preferences.selectedRagReleaseId;
  const preferredVariantId = preferences.selectedRagVariantId;
  const preferredSnapshotId = preferences.selectedCorpusSnapshotId;

  const idempotent = useIdempotentReleaseAction();

  const [load, setLoad] = useState<ReleaseLoadState>(
    projectId ? { status: "loading" } : { status: "no-project" },
  );
  const [buildReport, setBuildReport] = useState<BuildReportState>({ status: "idle" });
  const [notice, setNotice] = useState<ReleaseWorkspaceNotice>(null);
  const [creating, setCreating] = useState(false);
  // Intención de mutación en vuelo sobre la release seleccionada (deshabilita las
  // acciones y evita doble envío). null = ninguna.
  const [busyAction, setBusyAction] = useState<null | "build" | "validate" | "publish" | "retire">(
    null,
  );

  // Selección local del draft (estado de formulario, no persistido). Se siembra con
  // las preferencias de navegación y un fallback al primer elemento cargado.
  const [draftVariantId, setDraftVariantId] = useState<string | null>(null);
  const [draftSnapshotId, setDraftSnapshotId] = useState<string | null>(null);
  const [draftBindingKey, setDraftBindingKey] = useState<string | null>(null);

  // Un único AbortController vivo: cambiar de proyecto o refrescar abortan la carga
  // en vuelo para evitar condiciones de carrera entre proyectos.
  const controllerRef = useRef<AbortController | null>(null);

  const fetchAll = useCallback(async (pid: string, signal: AbortSignal) => {
    setLoad({ status: "loading" });
    try {
      // Los tres listados recorren TODAS las páginas: releases, variantes y
      // snapshots son la evidencia del ciclo RAG y ninguna puede quedar truncada
      // en la primera página (25 ítems).
      const [allReleases, allVariants, allSnapshots, configuration] = await Promise.all([
        listAllReleases(pid, { signal }),
        listAllVariants(pid, { signal }),
        listAllCorpusSnapshots(pid, { signal }),
        getConfiguration(pid, { signal }),
      ]);
      if (signal.aborted) {
        return;
      }
      setLoad({
        status: "ready",
        data: {
          releases: Array.isArray(allReleases) ? allReleases : [],
          variants: Array.isArray(allVariants) ? allVariants : [],
          snapshots: Array.isArray(allSnapshots) ? allSnapshots : [],
          // `target_binding_key` es una clave LÓGICA; nunca el `indexing_target_id`
          // físico. Se leen de la configuración versionada (read-only).
          bindingKeys: Array.isArray(configuration.target_bindings)
            ? configuration.target_bindings.map((binding) => binding.binding_key)
            : [],
        },
      });
    } catch (error) {
      if (signal.aborted) {
        return;
      }
      const message = messageFromError(error);
      setLoad({ status: "error", message });
      setNotice({ tone: "danger", message });
    }
  }, []);

  const runLoad = useCallback(
    (pid: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      void fetchAll(pid, controller.signal);
    },
    [fetchAll],
  );

  // Al cambiar de proyecto se recarga todo y se reinicia el draft/notice/report. La
  // selección de proyecto obsoleta limpia el estado local antes de recargar.
  useEffect(() => {
    setNotice(null);
    setBuildReport({ status: "idle" });
    setDraftVariantId(null);
    setDraftSnapshotId(null);
    setDraftBindingKey(null);
    if (!projectId) {
      controllerRef.current?.abort();
      controllerRef.current = null;
      setLoad({ status: "no-project" });
      return;
    }
    runLoad(projectId);
    return () => {
      controllerRef.current?.abort();
    };
  }, [projectId, runLoad]);

  const data = load.status === "ready" ? load.data : null;

  // Siembra las selecciones del draft cuando llegan los datos: preferencia de
  // navegación si sigue siendo válida, si no el primer elemento disponible.
  useEffect(() => {
    if (!data) {
      return;
    }
    setDraftVariantId((current) => {
      if (current && data.variants.some((v) => v.rag_variant_id === current)) {
        return current;
      }
      const preferred = data.variants.find((v) => v.rag_variant_id === preferredVariantId);
      return preferred?.rag_variant_id ?? data.variants[0]?.rag_variant_id ?? null;
    });
    setDraftSnapshotId((current) => {
      if (current && data.snapshots.some((s) => s.corpus_snapshot_id === current)) {
        return current;
      }
      const preferred = data.snapshots.find((s) => s.corpus_snapshot_id === preferredSnapshotId);
      return preferred?.corpus_snapshot_id ?? data.snapshots[0]?.corpus_snapshot_id ?? null;
    });
    setDraftBindingKey((current) => {
      if (current && data.bindingKeys.includes(current)) {
        return current;
      }
      return data.bindingKeys[0] ?? null;
    });
  }, [data, preferredVariantId, preferredSnapshotId]);

  const selectedRelease = useMemo(() => {
    if (!data || !selectedReleaseId) {
      return null;
    }
    return data.releases.find((release) => release.rag_release_id === selectedReleaseId) ?? null;
  }, [data, selectedReleaseId]);

  // Reemplaza (o inserta al frente) una release en la lista tras una mutación, sin
  // recargar toda la página.
  const applyRelease = useCallback((updated: Release) => {
    setLoad((current) => {
      if (current.status !== "ready") {
        return current;
      }
      const releases = current.data.releases.some((r) => r.rag_release_id === updated.rag_release_id)
        ? current.data.releases.map((r) =>
            r.rag_release_id === updated.rag_release_id ? updated : r,
          )
        : [updated, ...current.data.releases];
      return { status: "ready", data: { ...current.data, releases } };
    });
  }, []);

  // Fallo de una mutación: un `INVALID_RELEASE_TRANSITION` resincroniza el estado
  // real (refetch) en vez de forzar la transición; el resto se surfacea fail-closed.
  const handleMutationError = useCallback(
    async (error: unknown, releaseId: string) => {
      const mapped = mapPipelineError(error);
      if (mapped.code === "INVALID_RELEASE_TRANSITION") {
        try {
          const fresh = await getRelease(releaseId);
          applyRelease(fresh);
          setNotice({
            tone: "warning",
            message: `Transición inválida: el estado real de la release es "${fresh.state}". Se resincronizó; no se forzó la transición.`,
          });
          return;
        } catch (refetchError) {
          setNotice({ tone: "danger", message: messageFromError(refetchError) });
          return;
        }
      }
      setNotice({ tone: "danger", message: messageFromError(error) });
    },
    [applyRelease],
  );

  const createDraft = useCallback(async (): Promise<boolean> => {
    if (!projectId || !draftVariantId || !draftSnapshotId || !draftBindingKey) {
      return false;
    }
    setCreating(true);
    setNotice(null);
    try {
      // Body EXACTO del contrato: solo claves lógicas, nunca IDs físicos.
      const release = await createReleaseDraft({
        corpus_snapshot_id: draftSnapshotId,
        rag_variant_id: draftVariantId,
        target_binding_key: draftBindingKey,
      });
      applyRelease(release);
      setSelectedRagRelease(release.rag_release_id);
      setBuildReport({ status: "idle" });
      setNotice({
        tone: "success",
        message: `Draft ${release.rag_release_id} (release #${release.release_number}) creado en estado "${release.state}".`,
      });
      return true;
    } catch (error) {
      setNotice({ tone: "danger", message: messageFromError(error) });
      return false;
    } finally {
      setCreating(false);
    }
  }, [projectId, draftVariantId, draftSnapshotId, draftBindingKey, applyRelease, setSelectedRagRelease]);

  const build = useCallback(async () => {
    if (!selectedRelease || busyAction) {
      return;
    }
    const releaseId = selectedRelease.rag_release_id;
    setBusyAction("build");
    setNotice(null);
    try {
      const report = await idempotent.run(`build:${releaseId}`, (options) =>
        buildRelease(releaseId, options),
      );
      setBuildReport({ status: "success", report });
      setNotice({
        tone: "success",
        message: `Build completado: ${report.revisions_built} revisión(es), ${report.built_stages} etapa(s) construida(s), ${report.reused_stages} reutilizada(s).`,
      });
    } catch (error) {
      await handleMutationError(error, releaseId);
    } finally {
      setBusyAction(null);
    }
  }, [selectedRelease, busyAction, idempotent, handleMutationError]);

  const validate = useCallback(async () => {
    if (!selectedRelease || busyAction) {
      return;
    }
    const releaseId = selectedRelease.rag_release_id;
    setBusyAction("validate");
    setNotice(null);
    try {
      const updated = await idempotent.run(`validate:${releaseId}`, (options) =>
        validateRelease(releaseId, options),
      );
      applyRelease(updated);
      setNotice({ tone: "success", message: `Release validada (estado "${updated.state}").` });
    } catch (error) {
      await handleMutationError(error, releaseId);
    } finally {
      setBusyAction(null);
    }
  }, [selectedRelease, busyAction, idempotent, applyRelease, handleMutationError]);

  const publish = useCallback(async () => {
    if (!selectedRelease || busyAction) {
      return;
    }
    const releaseId = selectedRelease.rag_release_id;
    setBusyAction("publish");
    setNotice(null);
    try {
      const updated = await idempotent.run(`publish:${releaseId}`, (options) =>
        publishRelease(releaseId, options),
      );
      applyRelease(updated);
      setNotice({ tone: "success", message: `Release publicada (estado "${updated.state}").` });
    } catch (error) {
      await handleMutationError(error, releaseId);
    } finally {
      setBusyAction(null);
    }
  }, [selectedRelease, busyAction, idempotent, applyRelease, handleMutationError]);

  const retire = useCallback(
    async (reason: string): Promise<boolean> => {
      if (!selectedRelease || busyAction) {
        return false;
      }
      const trimmed = reason.trim();
      if (trimmed.length === 0) {
        setNotice({ tone: "warning", message: "Retirar exige un motivo explícito." });
        return false;
      }
      const releaseId = selectedRelease.rag_release_id;
      setBusyAction("retire");
      setNotice(null);
      try {
        const updated = await idempotent.run(`retire:${releaseId}`, (options) =>
          retireRelease(releaseId, { reason: trimmed }, options),
        );
        applyRelease(updated);
        setNotice({ tone: "success", message: `Release retirada (estado "${updated.state}").` });
        return true;
      } catch (error) {
        await handleMutationError(error, releaseId);
        return false;
      } finally {
        setBusyAction(null);
      }
    },
    [selectedRelease, busyAction, idempotent, applyRelease, handleMutationError],
  );

  const selectRelease = useCallback(
    (releaseId: string) => {
      setSelectedRagRelease(releaseId);
      // Cambiar de release descarta el informe de build de la anterior.
      setBuildReport({ status: "idle" });
      setNotice(null);
    },
    [setSelectedRagRelease],
  );

  const refresh = useCallback(() => {
    if (projectId) {
      runLoad(projectId);
    }
  }, [projectId, runLoad]);

  const canCreateDraft =
    !creating && draftVariantId !== null && draftSnapshotId !== null && draftBindingKey !== null;

  return {
    projectId,
    load,
    selectedReleaseId,
    selectedRelease,
    buildReport,
    notice,
    creating,
    busyAction,
    canCreateDraft,
    draftVariantId,
    draftSnapshotId,
    draftBindingKey,
    setDraftVariantId,
    setDraftSnapshotId,
    setDraftBindingKey,
    createDraft,
    build,
    validate,
    publish,
    retire,
    selectRelease,
    refresh,
  };
}
