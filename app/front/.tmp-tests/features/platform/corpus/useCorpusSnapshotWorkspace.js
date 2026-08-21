import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createCorpusSnapshot, listAllCorpusSnapshots, listAllDocuments, } from "../platformApi.js";
import { usePlatformPreferences } from "../hooks/usePlatformPreferences.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
function isNeedsReview(revision) {
    // `review_state` es la autoridad de elegibilidad de release (RevisionReviewState);
    // una revisión `needs_review` no es releaseable solo por estar normalizada.
    return revision.review_state === "needs_review";
}
function isBulkSelectableCandidate(revision) {
    // Fail-closed: una revisión `needs_review` solo entra al snapshot con inclusión
    // explícita del operador; "seleccionar todos" nunca la auto-incluye.
    return !isNeedsReview(revision);
}
// Traducción fail-closed de errores de transporte a copia de UI. Nunca oculta un
// bloqueo tras un genérico ni tras un éxito.
function messageFromError(error) {
    const mapped = mapPipelineError(error);
    if (mapped.status === 403) {
        return "No autorizado para esta operación.";
    }
    if (mapped.status === 503 && mapped.code === "HTTP_AUTH_NOT_CONFIGURED") {
        return "Problema de configuración del servidor de auth, no de tu sesión.";
    }
    if (mapped.status === 409) {
        return "Una revisión seleccionada es inválida o pertenece a otro proyecto. Revisa la selección; no se reintenta en silencio.";
    }
    // 422 (RevisionNotReleaseEligible/validación) y el resto: mensaje del backend
    // tal cual (campo concreto), sin ocultarlo.
    return mapped.message;
}
export function useCorpusSnapshotWorkspace() {
    // scope = null: este workspace solo lee la selección de proyecto vigente y
    // persiste el snapshot elegido (D6: solo IDs de navegación).
    const { preferences, setSelectedCorpusSnapshot } = usePlatformPreferences(null);
    const projectId = preferences.selectedProjectId;
    const selectedSnapshotId = preferences.selectedCorpusSnapshotId;
    const [candidates, setCandidates] = useState(projectId ? { status: "loading" } : { status: "no-project" });
    const [history, setHistory] = useState(projectId ? { status: "loading" } : { status: "idle" });
    const [selectedRevisionIds, setSelectedRevisionIds] = useState(new Set());
    // Decisión explícita por revisión `needs_review` seleccionada.
    const [decisions, setDecisions] = useState({});
    const [notice, setNotice] = useState(null);
    const [creating, setCreating] = useState(false);
    // Un único AbortController vivo: cambiar de proyecto o refrescar abortan la carga
    // en vuelo para evitar condiciones de carrera entre proyectos.
    const controllerRef = useRef(null);
    const load = useCallback(async (pid, signal) => {
        setCandidates({ status: "loading" });
        setHistory({ status: "loading" });
        try {
            const [allRevisions, snapshots] = await Promise.all([
                listAllDocuments(pid, { signal }),
                listAllCorpusSnapshots(pid, { signal }),
            ]);
            if (signal.aborted) {
                return;
            }
            // Solo las normalizadas pueden entrar a un snapshot.
            const eligible = allRevisions.filter((revision) => revision.normalized_registered);
            setCandidates(eligible.length === 0 ? { status: "empty" } : { status: "ready", revisions: eligible });
            setHistory(snapshots.length === 0 ? { status: "empty" } : { status: "ready", snapshots });
        }
        catch (error) {
            if (signal.aborted) {
                return;
            }
            const message = messageFromError(error);
            setCandidates({ status: "error", message });
            setHistory({ status: "error", message });
            setNotice({ tone: "danger", message });
        }
    }, []);
    const runLoad = useCallback((pid) => {
        controllerRef.current?.abort();
        const controller = new AbortController();
        controllerRef.current = controller;
        void load(pid, controller.signal);
    }, [load]);
    // Al cambiar de proyecto se reinicia selección/decisiones y se recarga todo. La
    // selección de proyecto obsoleta limpia la selección local antes de recargar.
    useEffect(() => {
        setSelectedRevisionIds(new Set());
        setDecisions({});
        setNotice(null);
        if (!projectId) {
            controllerRef.current?.abort();
            controllerRef.current = null;
            setCandidates({ status: "no-project" });
            setHistory({ status: "idle" });
            return;
        }
        runLoad(projectId);
        return () => {
            controllerRef.current?.abort();
        };
    }, [projectId, runLoad]);
    const toggleRevision = useCallback((revisionId) => {
        setNotice(null);
        setSelectedRevisionIds((current) => {
            const next = new Set(current);
            if (next.has(revisionId)) {
                next.delete(revisionId);
            }
            else {
                next.add(revisionId);
            }
            return next;
        });
        // Deseleccionar una revisión descarta su decisión (no se envía elegibilidad
        // de una revisión que ya no está en el snapshot).
        setDecisions((current) => {
            if (!(revisionId in current)) {
                return current;
            }
            const next = { ...current };
            delete next[revisionId];
            return next;
        });
    }, []);
    const setDecision = useCallback((revisionId, decision) => {
        setNotice(null);
        setDecisions((current) => ({ ...current, [revisionId]: decision }));
    }, []);
    const selectAllEligibleRevisions = useCallback(() => {
        setNotice(null);
        setSelectedRevisionIds(candidates.status === "ready"
            ? new Set(candidates.revisions
                .filter(isBulkSelectableCandidate)
                .map((revision) => revision.source_document_revision_id))
            : new Set());
        // La selección masiva fail-closed nunca incluye `needs_review`, así que toda
        // decisión previa asociada a revisiones no seleccionadas deja de aplicar.
        setDecisions({});
    }, [candidates]);
    const clearRevisionSelection = useCallback(() => {
        setNotice(null);
        setSelectedRevisionIds(new Set());
        setDecisions({});
    }, []);
    // Revisiones `needs_review` seleccionadas que aún no tienen decisión de inclusión:
    // el snapshot no puede crearse hasta resolverlas (gate fail-closed cliente).
    const pendingReviewIds = useMemo(() => {
        if (candidates.status !== "ready") {
            return [];
        }
        return candidates.revisions
            .filter((r) => selectedRevisionIds.has(r.source_document_revision_id) && isNeedsReview(r))
            .map((r) => r.source_document_revision_id)
            .filter((id) => decisions[id] === undefined);
    }, [candidates, selectedRevisionIds, decisions]);
    const canCreate = selectedRevisionIds.size > 0 && pendingReviewIds.length === 0 && !creating;
    const bulkSelectableRevisionIds = candidates.status === "ready"
        ? candidates.revisions
            .filter(isBulkSelectableCandidate)
            .map((revision) => revision.source_document_revision_id)
        : [];
    const bulkSelectableRevisionCount = bulkSelectableRevisionIds.length;
    const allBulkSelectableSelected = bulkSelectableRevisionCount > 0 &&
        bulkSelectableRevisionIds.every((revisionId) => selectedRevisionIds.has(revisionId));
    const createSnapshot = useCallback(async () => {
        if (!projectId || selectedRevisionIds.size === 0 || pendingReviewIds.length > 0) {
            return false;
        }
        setCreating(true);
        setNotice(null);
        try {
            const documentRevisionIds = Array.from(selectedRevisionIds);
            // eligibility_decisions solo lleva las revisiones que exigieron decisión
            // explícita (needs_review incluidas); las `processed` son `not_required`
            // implícito server-side y no se envían.
            const eligibilityDecisions = {};
            for (const revisionId of documentRevisionIds) {
                const decision = decisions[revisionId];
                if (decision !== undefined) {
                    eligibilityDecisions[revisionId] = decision;
                }
            }
            const hasDecisions = Object.keys(eligibilityDecisions).length > 0;
            const snapshot = await createCorpusSnapshot({
                project_id: projectId,
                document_revision_ids: documentRevisionIds,
                ...(hasDecisions ? { eligibility_decisions: eligibilityDecisions } : {}),
            });
            // Solo se persiste el ID de navegación del snapshot (D6): nunca documentos,
            // manifest ni decisiones.
            setSelectedCorpusSnapshot(snapshot.corpus_snapshot_id);
            setSelectedRevisionIds(new Set());
            setDecisions({});
            setNotice({
                tone: "success",
                message: `Snapshot ${snapshot.corpus_snapshot_id} creado (${snapshot.document_count} documento(s)).`,
            });
            runLoad(projectId);
            return true;
        }
        catch (error) {
            // 409 (revisión inválida/cross-project) y 422 (needs_review sin decisión
            // válida) se surfacean sin reintentar en silencio.
            setNotice({ tone: "danger", message: messageFromError(error) });
            return false;
        }
        finally {
            setCreating(false);
        }
    }, [projectId, selectedRevisionIds, pendingReviewIds, decisions, setSelectedCorpusSnapshot, runLoad]);
    const refresh = useCallback(() => {
        if (projectId) {
            runLoad(projectId);
        }
    }, [projectId, runLoad]);
    return {
        projectId,
        selectedSnapshotId,
        candidates,
        history,
        selectedRevisionIds,
        decisions,
        pendingReviewIds,
        notice,
        creating,
        canCreate,
        bulkSelectableRevisionCount,
        allBulkSelectableSelected,
        toggleRevision,
        selectAllEligibleRevisions,
        clearRevisionSelection,
        setDecision,
        createSnapshot,
        refresh,
    };
}
