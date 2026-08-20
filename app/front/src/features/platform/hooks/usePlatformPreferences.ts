import { useCallback, useEffect, useState } from "react";

import {
  readPlatformPreferences,
  writePlatformPreferences,
} from "../platformPersistence.js";
import {
  DEFAULT_PLATFORM_PREFERENCES,
  platformPreferencesEqual,
  resolvePlatformPreferences,
  type PlatformPreferences,
  type PlatformSelectionScope,
} from "../platformState.js";

// Preferencias de navegación de plataforma con rehidratación fail-closed. `scope`
// es la data ya cargada (IDs vivos, scope-filtrados por el backend); cuando llega,
// se limpian selecciones obsoletas/fuera-de-scope. Estado sensible (sesión,
// requests, idempotency) nunca entra aquí.
export function usePlatformPreferences(scope: PlatformSelectionScope | null) {
  const [preferences, setPreferences] = useState<PlatformPreferences>(() =>
    resolvePlatformPreferences({ stored: readPlatformPreferences(), scope: null }),
  );

  useEffect(() => {
    if (!scope) {
      return;
    }
    setPreferences((current) => {
      const next = resolvePlatformPreferences({ stored: current, scope });
      // Referencia estable si nada cambió: evita re-render/persist innecesarios.
      return platformPreferencesEqual(current, next) ? current : next;
    });
  }, [scope]);

  useEffect(() => {
    writePlatformPreferences(preferences);
  }, [preferences]);

  const setSelectedProject = useCallback((selectedProjectId: string | null) => {
    setPreferences((current) => {
      if (current.selectedProjectId === selectedProjectId) {
        return current;
      }
      // Cascada: cambiar de proyecto invalida variante/snapshot/release previos.
      return { ...DEFAULT_PLATFORM_PREFERENCES, selectedProjectId };
    });
  }, []);

  const setSelectedRagVariant = useCallback((selectedRagVariantId: string | null) => {
    setPreferences((current) =>
      current.selectedRagVariantId === selectedRagVariantId
        ? current
        : { ...current, selectedRagVariantId },
    );
  }, []);

  const setSelectedCorpusSnapshot = useCallback((selectedCorpusSnapshotId: string | null) => {
    setPreferences((current) =>
      current.selectedCorpusSnapshotId === selectedCorpusSnapshotId
        ? current
        : { ...current, selectedCorpusSnapshotId },
    );
  }, []);

  const setSelectedRagRelease = useCallback((selectedRagReleaseId: string | null) => {
    setPreferences((current) =>
      current.selectedRagReleaseId === selectedRagReleaseId
        ? current
        : { ...current, selectedRagReleaseId },
    );
  }, []);

  return {
    preferences,
    setSelectedProject,
    setSelectedRagVariant,
    setSelectedCorpusSnapshot,
    setSelectedRagRelease,
  };
}
