// Estado de selección persistible de la plataforma (Fase 8, Task 5).
//
// Solo IDs de navegación: proyecto y sus artefactos seleccionados. La lógica de
// reconciliación es pura y sin negocio (valida contra listas ya cargadas y limpia
// lo obsoleto/fuera-de-scope). NO vive aquí nada sensible: sesión, requests en
// curso, idempotency keys ni drafts — eso es estado runtime del componente.
export const DEFAULT_PLATFORM_PREFERENCES = {
    selectedProjectId: null,
    selectedRagVariantId: null,
    selectedCorpusSnapshotId: null,
    selectedRagReleaseId: null,
};
function keepIfPresent(id, ids) {
    return id !== null && ids.includes(id) ? id : null;
}
export function platformPreferencesEqual(a, b) {
    return (a.selectedProjectId === b.selectedProjectId &&
        a.selectedRagVariantId === b.selectedRagVariantId &&
        a.selectedCorpusSnapshotId === b.selectedCorpusSnapshotId &&
        a.selectedRagReleaseId === b.selectedRagReleaseId);
}
// Reconciliación fail-closed. `scope === null` = data aún no cargada → se preserva
// lo persistido (no se borra por falta de evidencia). Con scope: un proyecto
// ausente/fuera-de-scope limpia TODO (cascada); si el proyecto es válido, cada
// dependiente que ya no pertenezca se limpia individualmente.
export function resolvePlatformPreferences(options) {
    const base = options.stored ?? DEFAULT_PLATFORM_PREFERENCES;
    if (!options.scope) {
        return { ...base };
    }
    const selectedProjectId = keepIfPresent(base.selectedProjectId, options.scope.projectIds);
    if (selectedProjectId === null) {
        return { ...DEFAULT_PLATFORM_PREFERENCES };
    }
    return {
        selectedProjectId,
        selectedRagVariantId: keepIfPresent(base.selectedRagVariantId, options.scope.variantIds),
        selectedCorpusSnapshotId: keepIfPresent(base.selectedCorpusSnapshotId, options.scope.corpusSnapshotIds),
        selectedRagReleaseId: keepIfPresent(base.selectedRagReleaseId, options.scope.releaseIds),
    };
}
