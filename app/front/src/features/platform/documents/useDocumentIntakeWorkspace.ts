import { useCallback, useEffect, useRef, useState } from "react";

import {
  listAllDocuments,
  listVariants,
  normalizeDocuments,
  uploadDocument,
} from "../platformApi.js";
import { usePlatformPreferences } from "../hooks/usePlatformPreferences.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
import type {
  ProjectDocumentRevision,
  ProjectNormalizeReport,
  Variant,
} from "../platformTypes.js";

// Estado de servidor + acciones del workspace de intake documental. Los
// componentes reciben datos ya resueltos y callbacks; no hacen fetch ni traducen
// errores. Ninguna lógica de negocio documental/RAG vive aquí: solo orquesta el
// cliente HTTP y traduce estados a copia fail-closed.

// Unión discriminada del listado de revisiones. `no-project` (nada seleccionado)
// es distinto de `empty` (proyecto sin documentos): la copia direccional cambia.
export type DocumentsState =
  | { status: "no-project" }
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; revisions: ProjectDocumentRevision[] }
  | { status: "error"; message: string };

// Estado del selector de variante (la normalización va SIEMPRE por rag_variant_id,
// invariante D8: nunca por un processing_profile_id libre).
export type VariantsState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; variants: Variant[] }
  | { status: "error"; message: string };

export type DocumentWorkspaceNotice =
  | { tone: "info" | "success" | "warning" | "danger"; message: string }
  | null;

// Traducción fail-closed de errores de transporte a copia de UI. Cada rama surfacea
// el motivo real; nunca se oculta un bloqueo tras un genérico ni tras un éxito.
function messageFromError(error: unknown): string {
  const mapped = mapPipelineError(error);
  if (mapped.status === 403) {
    return "No autorizado para esta operación.";
  }
  if (mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED") {
    return "Problema de configuración del servidor de auth, no de tu sesión.";
  }
  if (mapped.status === 409 && mapped.code === "REVISION_PROJECT_MISMATCH") {
    return "Una revisión seleccionada pertenece a otro proyecto. Revisa la selección; no se reintenta en silencio.";
  }
  if (mapped.status === 409 && mapped.code === "VARIANT_PROJECT_MISMATCH") {
    return "La variante elegida pertenece a otro proyecto. Elige una variante de este proyecto; no se reintenta en silencio.";
  }
  // 422 (PROJECT_NORMALIZATION_INCOMPLETE/validación) y el resto: se muestra el
  // mensaje del backend tal cual (campo concreto), sin ocultarlo.
  return mapped.message;
}

export function useDocumentIntakeWorkspace() {
  // scope = null: este workspace solo lee la selección de proyecto vigente.
  const { preferences } = usePlatformPreferences(null);
  const projectId = preferences.selectedProjectId;

  const [documents, setDocuments] = useState<DocumentsState>(
    projectId ? { status: "loading" } : { status: "no-project" },
  );
  const [variants, setVariants] = useState<VariantsState>(
    projectId ? { status: "loading" } : { status: "idle" },
  );
  const [selectedRevisionIds, setSelectedRevisionIds] = useState<ReadonlySet<string>>(new Set());
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [force, setForce] = useState(false);
  const [notice, setNotice] = useState<DocumentWorkspaceNotice>(null);
  const [uploading, setUploading] = useState(false);
  const [normalizing, setNormalizing] = useState(false);
  const [lastUploadedRevisionId, setLastUploadedRevisionId] = useState<string | null>(null);
  const [report, setReport] = useState<ProjectNormalizeReport | null>(null);

  // Un único AbortController vivo: cambiar de proyecto o refrescar abortan la
  // carga en vuelo para evitar condiciones de carrera entre proyectos.
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async (pid: string, signal: AbortSignal) => {
    setDocuments({ status: "loading" });
    setVariants({ status: "loading" });
    try {
      // Documentos y variantes del mismo proyecto/scope comparten fallo de auth:
      // una sola rama de error fail-closed basta y no muestra parciales.
      // `listAllDocuments` recorre TODAS las páginas: el operador ve el corpus
      // completo, no solo los primeros 25.
      const [allRevisions, variantPage] = await Promise.all([
        listAllDocuments(pid, { signal }),
        listVariants(pid, undefined, { signal }),
      ]);
      if (signal.aborted) {
        return;
      }
      const revisions = Array.isArray(allRevisions) ? allRevisions : [];
      setDocuments(
        revisions.length === 0 ? { status: "empty" } : { status: "ready", revisions },
      );
      const items = Array.isArray(variantPage.items) ? variantPage.items : [];
      setVariants(items.length === 0 ? { status: "empty" } : { status: "ready", variants: items });
    } catch (error) {
      if (signal.aborted) {
        return;
      }
      const message = messageFromError(error);
      setDocuments({ status: "error", message });
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

  // Al cambiar de proyecto se reinicia selección/variante/report y se recarga todo.
  useEffect(() => {
    setSelectedRevisionIds(new Set());
    setSelectedVariantId(null);
    setForce(false);
    setNotice(null);
    setLastUploadedRevisionId(null);
    setReport(null);
    if (!projectId) {
      controllerRef.current?.abort();
      controllerRef.current = null;
      setDocuments({ status: "no-project" });
      setVariants({ status: "idle" });
      return;
    }
    runLoad(projectId);
    return () => {
      controllerRef.current?.abort();
    };
  }, [projectId, runLoad]);

  const toggleRevision = useCallback((revisionId: string) => {
    setNotice(null);
    setSelectedRevisionIds((current) => {
      const next = new Set(current);
      if (next.has(revisionId)) {
        next.delete(revisionId);
      } else {
        next.add(revisionId);
      }
      return next;
    });
  }, []);

  // Selección masiva sobre el corpus cargado (todas las páginas). Sin esto,
  // marcar decenas de revisiones a mano es inviable.
  const selectAllRevisions = useCallback(() => {
    setNotice(null);
    setSelectedRevisionIds(
      documents.status === "ready"
        ? new Set(documents.revisions.map((r) => r.source_document_revision_id))
        : new Set(),
    );
  }, [documents]);

  const clearRevisionSelection = useCallback(() => {
    setNotice(null);
    setSelectedRevisionIds(new Set());
  }, []);

  const selectVariant = useCallback((variantId: string) => {
    setNotice(null);
    setSelectedVariantId(variantId || null);
  }, []);

  const toggleForce = useCallback(() => {
    setForce((current) => !current);
  }, []);

  // Upload y normalize NO se reintentan automáticamente: no son idempotentes y no
  // hay Idempotency-Key en este lane. Cada intento es un click explícito.
  const upload = useCallback(
    async (file: File, sourceRelpath: string): Promise<boolean> => {
      if (!projectId) {
        return false;
      }
      setUploading(true);
      setNotice(null);
      setLastUploadedRevisionId(null);
      try {
        // El cliente solo manda file + source_relpath (lógico/relativo). El hash,
        // el tamaño, el target físico y el actor los calcula/resuelve el servidor.
        const revision = await uploadDocument(projectId, file, sourceRelpath);
        setLastUploadedRevisionId(revision.source_document_revision_id);
        setNotice({
          tone: "success",
          message: `Documento registrado como ${revision.source_document_revision_id}.`,
        });
        runLoad(projectId);
        return true;
      } catch (error) {
        setNotice({ tone: "danger", message: messageFromError(error) });
        return false;
      } finally {
        setUploading(false);
      }
    },
    [projectId, runLoad],
  );

  const normalize = useCallback(async (): Promise<boolean> => {
    if (!projectId || !selectedVariantId || selectedRevisionIds.size === 0) {
      return false;
    }
    setNormalizing(true);
    setNotice(null);
    setReport(null);
    try {
      // La normalización va EXCLUSIVAMENTE por rag_variant_id (invariante D8):
      // nunca por un processing_profile_id libre.
      const result = await normalizeDocuments(projectId, {
        rag_variant_id: selectedVariantId,
        document_revision_ids: Array.from(selectedRevisionIds),
        force,
      });
      setReport(result);
      const tone = result.needs_review > 0 ? "warning" : "success";
      setNotice({
        tone,
        message:
          result.needs_review > 0
            ? `Normalización terminada: ${result.needs_review} revisión(es) requieren atención (needs_review).`
            : `Normalización terminada: ${result.processed} procesada(s).`,
      });
      // Las revisiones procesadas se deseleccionan y se refresca la lista para
      // reflejar normalized_registered/processing_status reales.
      setSelectedRevisionIds(new Set());
      runLoad(projectId);
      return true;
    } catch (error) {
      // 409 cross-project (revisión/variante de otro proyecto) y 422 se surfacean
      // sin reintentar en silencio; el motivo real queda visible.
      setNotice({ tone: "danger", message: messageFromError(error) });
      return false;
    } finally {
      setNormalizing(false);
    }
  }, [projectId, selectedVariantId, selectedRevisionIds, force, runLoad]);

  const refresh = useCallback(() => {
    if (projectId) {
      runLoad(projectId);
    }
  }, [projectId, runLoad]);

  const canNormalize =
    selectedVariantId !== null && selectedRevisionIds.size > 0 && !normalizing;

  return {
    projectId,
    documents,
    variants,
    selectedRevisionIds,
    selectedVariantId,
    force,
    notice,
    uploading,
    normalizing,
    lastUploadedRevisionId,
    report,
    canNormalize,
    upload,
    toggleRevision,
    selectAllRevisions,
    clearRevisionSelection,
    selectVariant,
    toggleForce,
    normalize,
    refresh,
  };
}
