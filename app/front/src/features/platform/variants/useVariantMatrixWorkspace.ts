import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createVariant as apiCreateVariant,
  getVariantMatrix,
  listVariants,
} from "../platformApi.js";
import { usePlatformPreferences } from "../hooks/usePlatformPreferences.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
import type { Variant, VariantMatrixCell } from "../platformTypes.js";

// Estado de servidor + acciones del workspace de variantes. Los componentes
// reciben datos ya resueltos y callbacks; no hacen fetch ni traducen errores.

// Unión discriminada del estado de la matriz. `no-project` (nada seleccionado)
// es distinto de `empty` (config vigente sin celdas construibles): la copia
// direccional cambia según el caso. Nunca se colapsan en un booleano suelto.
export type MatrixState =
  | { status: "no-project" }
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; cells: VariantMatrixCell[] }
  | { status: "error"; message: string };

// Estado del listado de variantes ya existentes del proyecto.
export type VariantsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; variants: Variant[] }
  | { status: "error"; message: string };

export type VariantWorkspaceNotice =
  | { tone: "info" | "success" | "warning" | "danger"; message: string }
  | null;

// Traducción fail-closed de errores de transporte a copia de UI. El 409
// `STALE_VARIANT_MATRIX_CELL` NO pasa por aquí: se maneja en `submit` porque
// además refresca la matriz y limpia la selección. El resto (403/503/422/…)
// se surfacea sin ocultar el motivo real detrás de un genérico.
function messageFromError(error: unknown): string {
  const mapped = mapPipelineError(error);
  if (mapped.status === 403) {
    return "No autorizado para esta operación.";
  }
  if (mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED") {
    return "Problema de configuración del servidor de auth, no de tu sesión.";
  }
  return mapped.message;
}

export function useVariantMatrixWorkspace() {
  // scope = null: este workspace solo lee la selección de proyecto vigente. La
  // reconciliación full-scope pertenece a un provider posterior (igual que Projects).
  const { preferences } = usePlatformPreferences(null);
  const projectId = preferences.selectedProjectId;

  const [matrix, setMatrix] = useState<MatrixState>(
    projectId ? { status: "loading" } : { status: "no-project" },
  );
  const [variants, setVariants] = useState<VariantsState>(
    projectId ? { status: "loading" } : { status: "idle" },
  );
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [notice, setNotice] = useState<VariantWorkspaceNotice>(null);
  const [submitting, setSubmitting] = useState(false);

  // Un único AbortController vivo: cambiar de proyecto, refetch o submit abortan
  // la carga en vuelo para evitar condiciones de carrera entre proyectos.
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async (pid: string, signal: AbortSignal) => {
    setMatrix({ status: "loading" });
    setVariants({ status: "loading" });
    try {
      // Matriz y variantes del mismo proyecto/scope: comparten fallo de auth, así
      // que una sola rama de error fail-closed es suficiente y no muestra parciales.
      const [cells, page] = await Promise.all([
        getVariantMatrix(pid, { signal }),
        listVariants(pid, undefined, { signal }),
      ]);
      if (signal.aborted) {
        return;
      }
      setMatrix(cells.length === 0 ? { status: "empty" } : { status: "ready", cells });
      const items = Array.isArray(page.items) ? page.items : [];
      setVariants(
        items.length === 0 ? { status: "empty" } : { status: "ready", variants: items },
      );
    } catch (error) {
      if (signal.aborted) {
        return;
      }
      const message = messageFromError(error);
      setMatrix({ status: "error", message });
      setVariants({ status: "error", message });
      setNotice({ tone: "danger", message });
    }
  }, []);

  const runLoad = useCallback(
    (pid: string) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      void load(pid, controller.signal);
    },
    [load],
  );

  // Al cambiar de proyecto se reinicia selección/slug/notice y se recarga todo.
  useEffect(() => {
    setSelectedCellId(null);
    setSlug("");
    setNotice(null);
    if (!projectId) {
      controllerRef.current?.abort();
      controllerRef.current = null;
      setMatrix({ status: "no-project" });
      setVariants({ status: "idle" });
      return;
    }
    runLoad(projectId);
    return () => {
      controllerRef.current?.abort();
    };
  }, [projectId, runLoad]);

  // La celda seleccionada solo es válida si sigue en la matriz y es construible;
  // si tras un refetch desaparece o deja de ser construible, deja de contar.
  const cells = matrix.status === "ready" ? matrix.cells : [];
  const selectedCell = useMemo(
    () => cells.find((cell) => cell.cell_id === selectedCellId && cell.buildable) ?? null,
    [cells, selectedCellId],
  );

  const canSubmit = selectedCell !== null && slug.trim().length > 0 && !submitting;

  const selectCell = useCallback((cellId: string) => {
    setNotice(null);
    // Toggle explícito: reelegir la misma celda la deselecciona. Nunca se salta
    // a otra celda de forma implícita.
    setSelectedCellId((current) => (current === cellId ? null : cellId));
  }, []);

  const refetchMatrix = useCallback(() => {
    if (projectId) {
      runLoad(projectId);
    }
  }, [projectId, runLoad]);

  const submit = useCallback(async () => {
    if (!projectId || !selectedCellId) {
      return;
    }
    const variantSlug = slug.trim();
    if (!variantSlug) {
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      // INVARIANTE de seguridad (Fase 7): el body es EXCLUSIVAMENTE
      // {cell_id, variant_slug}. El target físico y los IDs de perfil viven en la
      // celda reconfirmada; jamás se envían desde el frontend.
      const variant = await apiCreateVariant(projectId, {
        cell_id: selectedCellId,
        variant_slug: variantSlug,
      });
      setSelectedCellId(null);
      setSlug("");
      setNotice({ tone: "success", message: `Variante ${variant.rag_variant_id} creada.` });
      // Crear una variante puede avanzar la configuración: se refresca matriz +
      // variantes para no operar sobre celdas obsoletas.
      runLoad(projectId);
    } catch (error) {
      const mapped = mapPipelineError(error);
      if (mapped.status === 409 && mapped.code === "STALE_VARIANT_MATRIX_CELL") {
        // La celda quedó obsoleta frente a la configuración vigente. Se refresca la
        // matriz y se LIMPIA la selección para forzar una reconfirmación explícita:
        // nunca se elige otra celda en silencio.
        setSelectedCellId(null);
        setNotice({
          tone: "warning",
          message:
            "La configuración cambió y la celda seleccionada quedó obsoleta. Revisa la matriz actualizada y vuelve a confirmar una celda.",
        });
        runLoad(projectId);
      } else {
        setNotice({ tone: "danger", message: messageFromError(error) });
      }
    } finally {
      setSubmitting(false);
    }
  }, [projectId, selectedCellId, slug, runLoad]);

  return {
    projectId,
    matrix,
    variants,
    selectedCellId,
    selectedCell,
    slug,
    notice,
    submitting,
    canSubmit,
    selectCell,
    setSlug,
    submit,
    refetchMatrix,
  };
}
