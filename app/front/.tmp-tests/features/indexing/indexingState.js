export const INDEXING_TERMINAL_STATUSES = [
    "completed",
    "failed",
    "cancelled",
    "blocked",
];
export function indexingRunIsTerminal(status) {
    return INDEXING_TERMINAL_STATUSES.includes(status);
}
// Activation is only possible once the run completed and has not been activated
// yet. This gate keeps activation as an explicit, separate operator action.
export function canActivateIndexingRun(run) {
    return run.status === "completed" && run.activationStatus === "pending";
}
// A run that failed after committing at least one document is partially complete.
export function indexingRunIsPartial(run) {
    return run.status === "failed" && run.summary.committedDocuments > 0;
}
// A document only counts as indexed when it has a commit timestamp.
export function indexingDocumentIsCommitted(document) {
    return document.committedAt !== null;
}
export function indexingRunStatusLabel(status) {
    if (status === "pending")
        return "Pendiente";
    if (status === "running")
        return "En ejecucion";
    if (status === "completed")
        return "Completada";
    if (status === "failed")
        return "Fallida";
    if (status === "cancelled")
        return "Cancelada";
    if (status === "blocked")
        return "Bloqueada";
    return "Desconocido";
}
export function indexingRunStatusTone(status) {
    if (status === "completed")
        return "success";
    if (status === "pending" || status === "running")
        return "warning";
    if (status === "failed" || status === "blocked")
        return "danger";
    if (status === "cancelled")
        return "neutral";
    return "neutral";
}
export function activationStatusLabel(status) {
    if (status === "pending")
        return "Pendiente";
    if (status === "active")
        return "Activa";
    if (status === "inactive")
        return "Inactiva";
    if (status === "rolled_back")
        return "Revertida";
    if (status === "blocked")
        return "Bloqueada";
    if (status === "legacy_unverified")
        return "Legacy sin verificar";
    return "Desconocido";
}
export function indexingRunProgressPercent(summary) {
    if (summary.requestedDocuments <= 0) {
        return 0;
    }
    return Math.min(100, Math.round((summary.committedDocuments / summary.requestedDocuments) * 100));
}
// The activation stage owns the handoff into retrieval, exposed as the returned
// retrieval_profile_id. Returns null until an activation produces one.
export function activationRetrievalProfileId(result) {
    return result.retrievalProfileId;
}
