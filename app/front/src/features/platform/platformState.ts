// Estado de selección persistible de la plataforma (Fase 8, Task 5).
//
// Solo IDs de navegación: proyecto y sus artefactos seleccionados. La lógica de
// reconciliación es pura y sin negocio (valida contra listas ya cargadas y limpia
// lo obsoleto/fuera-de-scope). NO vive aquí nada sensible: sesión, requests en
// curso, idempotency keys ni drafts — eso es estado runtime del componente.

export type PlatformPreferences = {
  selectedProjectId: string | null;
  selectedRagVariantId: string | null;
  selectedCorpusSnapshotId: string | null;
  selectedRagReleaseId: string | null;
};

export const DEFAULT_PLATFORM_PREFERENCES: PlatformPreferences = {
  selectedProjectId: null,
  selectedRagVariantId: null,
  selectedCorpusSnapshotId: null,
  selectedRagReleaseId: null,
};

// Identidades vivas contra las que se validan las selecciones persistidas. Solo
// IDs (no entidades): mantiene la reconciliación pura y barata. Los IDs de
// variante/snapshot/release son los del proyecto seleccionado (los carga el
// caller por proyecto).
export type PlatformSelectionScope = {
  projectIds: readonly string[];
  variantIds: readonly string[];
  corpusSnapshotIds: readonly string[];
  releaseIds: readonly string[];
};

function keepIfPresent(id: string | null, ids: readonly string[]): string | null {
  return id !== null && ids.includes(id) ? id : null;
}

export function platformPreferencesEqual(
  a: PlatformPreferences,
  b: PlatformPreferences,
): boolean {
  return (
    a.selectedProjectId === b.selectedProjectId &&
    a.selectedRagVariantId === b.selectedRagVariantId &&
    a.selectedCorpusSnapshotId === b.selectedCorpusSnapshotId &&
    a.selectedRagReleaseId === b.selectedRagReleaseId
  );
}

// Reconciliación fail-closed. `scope === null` = data aún no cargada → se preserva
// lo persistido (no se borra por falta de evidencia). Con scope: un proyecto
// ausente/fuera-de-scope limpia TODO (cascada); si el proyecto es válido, cada
// dependiente que ya no pertenezca se limpia individualmente.
export function resolvePlatformPreferences(options: {
  stored: PlatformPreferences | null;
  scope: PlatformSelectionScope | null;
}): PlatformPreferences {
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
    selectedCorpusSnapshotId: keepIfPresent(
      base.selectedCorpusSnapshotId,
      options.scope.corpusSnapshotIds,
    ),
    selectedRagReleaseId: keepIfPresent(base.selectedRagReleaseId, options.scope.releaseIds),
  };
}
