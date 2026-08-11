export const EMBEDDING_TERMINAL_STATUSES = [
    "completed",
    "failed",
    "cancelled",
    "blocked",
];
// The backend already publishes the effective document-embedding verdict in
// can_embed_documents, including any narrow operational waivers.
export function embeddingProfileSelectable(profile) {
    return profile.canEmbedDocuments;
}
// Returns a stable machine reason for why a profile cannot be selected today, or
// null when it is selectable. The compatibility_status carries the operative
// reason (e.g. compatibility_not_proven) once the profile is otherwise present.
export function embeddingProfileBlockedReason(profile) {
    if (embeddingProfileSelectable(profile)) {
        return null;
    }
    if (!profile.active) {
        return "inactive";
    }
    if (!profile.documentEnabled) {
        return profile.compatibilityStatus || "document_disabled";
    }
    return profile.compatibilityStatus || "compatibility_not_proven";
}
// The bundle inspection surface must use bundle-level chunk and validation links,
// never the removed run-documents/run-items endpoints. This normalizes and
// asserts the shape used by the inspector.
export function requiredEmbeddingBundleLinks(links) {
    return {
        chunks: links.chunks,
        validation: links.validation,
    };
}
export function embeddingRunIsTerminal(status) {
    return EMBEDDING_TERMINAL_STATUSES.includes(status);
}
export function embeddingRunStatusLabel(status) {
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
export function embeddingRunStatusTone(status) {
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
export function embeddingRunProgressPercent(summary) {
    if (summary.requestedChildren <= 0) {
        return 0;
    }
    return Math.min(100, Math.round((summary.embeddedChildren / summary.requestedChildren) * 100));
}
// A completed run pivots the detail pane to the produced embedding bundle. This
// returns the bundle id to inspect, or null when the run has not produced one.
export function embeddingRunProducedBundleId(run) {
    if (run.status === "completed" && run.producedEmbeddingBundleId) {
        return run.producedEmbeddingBundleId;
    }
    return null;
}
export function selectableEmbeddingProfiles(profiles) {
    return profiles.filter(embeddingProfileSelectable);
}
export function embeddingCatalogFullyBlocked(profiles) {
    return profiles.length > 0 && profiles.every((profile) => !embeddingProfileSelectable(profile));
}
