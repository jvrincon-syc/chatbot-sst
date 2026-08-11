export const DEFAULT_CHUNKING_PROFILE_ID = "local-structural-v1";
export function parseChunkingDocumentIds(raw) {
    const seen = new Set();
    const values = [];
    for (const token of raw.split(/[\s,]+/)) {
        const value = token.trim();
        if (!value || seen.has(value)) {
            continue;
        }
        seen.add(value);
        values.push(value);
    }
    return values;
}
export function createChunkingIdempotencyKey() {
    const cryptoObject = globalThis.crypto;
    if (cryptoObject?.randomUUID) {
        return `chunking-${cryptoObject.randomUUID()}`;
    }
    return `chunking-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
export function mergeChunkingFormState(current, next) {
    const merged = { ...current, ...next };
    const payloadChanged = current.scope !== merged.scope ||
        current.documentIdsInput !== merged.documentIdsInput ||
        current.profileId !== merged.profileId ||
        current.force !== merged.force;
    if (payloadChanged) {
        merged.idempotencyKey = createChunkingIdempotencyKey();
    }
    return merged;
}
export function chunkingRunProgressPercent(run) {
    if (run.requestedDocuments <= 0) {
        return 0;
    }
    return Math.min(100, Math.round((run.completedDocuments / run.requestedDocuments) * 100));
}
export function chunkingRunStatusLabel(status) {
    if (status === "queued")
        return "En cola";
    if (status === "running")
        return "En ejecucion";
    if (status === "completed")
        return "Completada";
    if (status === "completed_with_warnings")
        return "Completada con alertas";
    if (status === "interrupted")
        return "Interrumpida";
    if (status === "failed")
        return "Fallida";
    return "Desconocido";
}
export function chunkingRunStatusTone(status) {
    if (status === "completed")
        return "success";
    if (status === "completed_with_warnings" || status === "queued" || status === "interrupted") {
        return "warning";
    }
    if (status === "failed")
        return "danger";
    return "neutral";
}
export function chunkingRunIsTerminalStatus(status) {
    return (status === "completed" ||
        status === "completed_with_warnings" ||
        status === "failed" ||
        status === "interrupted");
}
export function chunkingScopeLabel(scope) {
    return scope === "corpus" ? "Corpus" : "Documentos";
}
export function chunkingPaginationLabel(page, totalPages, totalItems) {
    if (totalItems === 0) {
        return "Sin resultados";
    }
    return `Pagina ${page} de ${totalPages} · ${totalItems} items`;
}
export function chunkingProfileSummary(profile) {
    const overlapPercent = Math.round(profile.overlapRatio * 100);
    return `Min ${profile.childMinTokens} · Target ${profile.childTargetTokens} · Max ${profile.childMaxTokens} · Overlap ${overlapPercent}% (${profile.overlapMinTokens}-${profile.overlapMaxTokens})`;
}
