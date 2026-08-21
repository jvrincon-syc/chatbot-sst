// Persistencia de las preferencias de plataforma (Fase 8, Task 5).
//
// Mismo estilo que `dashboardPersistence`/`chunkingPersistence`: clave versionada,
// guard SSR (`typeof window`), try/catch silencioso, coerción campo a campo. Solo
// se serializan los 4 IDs de navegación — nunca sesión, bearer, requests ni
// idempotency keys (no viven en este tipo, así que no pueden filtrarse por aquí).
import { DEFAULT_PLATFORM_PREFERENCES, } from "./platformState.js";
const STORAGE_KEY = "chatbot-sst.platform.preferences.v1";
function isRecord(value) {
    return typeof value === "object" && value !== null;
}
function toStringOrNull(value) {
    return value === null || typeof value === "string" ? value : null;
}
function serializePlatformPreferences(value) {
    // Objeto explícito: nunca se persiste un campo no declarado.
    return JSON.stringify({
        selectedProjectId: value.selectedProjectId,
        selectedRagVariantId: value.selectedRagVariantId,
        selectedCorpusSnapshotId: value.selectedCorpusSnapshotId,
        selectedRagReleaseId: value.selectedRagReleaseId,
    });
}
function parseStoredPlatformPreferences(raw) {
    const parsed = JSON.parse(raw);
    if (!isRecord(parsed)) {
        return null;
    }
    return {
        selectedProjectId: toStringOrNull(parsed.selectedProjectId),
        selectedRagVariantId: toStringOrNull(parsed.selectedRagVariantId),
        selectedCorpusSnapshotId: toStringOrNull(parsed.selectedCorpusSnapshotId),
        selectedRagReleaseId: toStringOrNull(parsed.selectedRagReleaseId),
    };
}
export function serializePlatformPreferencesForTest(value) {
    return serializePlatformPreferences(value);
}
export function readPlatformPreferences() {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        return raw ? parseStoredPlatformPreferences(raw) : null;
    }
    catch {
        return null;
    }
}
export function writePlatformPreferences(value) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        window.localStorage.setItem(STORAGE_KEY, serializePlatformPreferences(value));
    }
    catch {
        // Ignora fallos de cuota o modo privado: la GUI funciona sin persistencia.
    }
}
// Reexport del default para que los consumidores no importen dos módulos por un
// caso de arranque (sin datos previos).
export { DEFAULT_PLATFORM_PREFERENCES };
