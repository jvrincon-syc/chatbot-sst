import { isLlamaRoute, routeFromStatus } from "../../llamaRoutes.js";
import { DEFAULT_LLAMA_CONTROLS, createDefaultDashboardPreferences, } from "./dashboardTypes.js";
import { isDashboardView } from "./dashboardNavigation.js";
const LEGACY_STORAGE_KEY = "chatbot-sst.dashboard.preferences.v1";
const STORAGE_KEY = "chatbot-sst.dashboard.preferences.v2";
function serializeDashboardPreferences(value) {
    return JSON.stringify({
        activeView: value.activeView,
        selectedDocumentIds: value.selectedDocumentIds,
        embeddingIndexing: value.embeddingIndexing,
    });
}
function isRecord(value) {
    return typeof value === "object" && value !== null;
}
function isProviderMode(value) {
    return value === "local" || value === "llama_cloud";
}
function isStringOrNull(value) {
    return value === null || typeof value === "string";
}
function isEmbeddingIndexingStage(value) {
    return (value === "embedding" ||
        value === "indexing" ||
        value === "activation" ||
        value === "retrieval");
}
function toStringOrNull(value) {
    return value === null || typeof value === "string" ? value : null;
}
function parseEmbeddingIndexingState(value) {
    const defaults = createDefaultDashboardPreferences().embeddingIndexing;
    if (!isRecord(value)) {
        return defaults;
    }
    return {
        activeStage: isEmbeddingIndexingStage(value.activeStage)
            ? value.activeStage
            : defaults.activeStage,
        selectedEmbeddingProfileId: toStringOrNull(value.selectedEmbeddingProfileId),
        selectedChunkBundleId: toStringOrNull(value.selectedChunkBundleId),
        activeEmbeddingRunId: toStringOrNull(value.activeEmbeddingRunId),
        selectedEmbeddingBundleId: toStringOrNull(value.selectedEmbeddingBundleId),
        activeIndexingRunId: toStringOrNull(value.activeIndexingRunId),
        activeActivationRunId: toStringOrNull(value.activeActivationRunId),
        selectedRetrievalProfileId: toStringOrNull(value.selectedRetrievalProfileId),
    };
}
function isLlamaControls(value) {
    return (isRecord(value) &&
        isProviderMode(value.providerMode) &&
        typeof value.route === "string" &&
        isLlamaRoute(value.route));
}
export function deriveLlamaControls(status) {
    if (!status) {
        return DEFAULT_LLAMA_CONTROLS;
    }
    return {
        providerMode: status.cloudEnabled ? "llama_cloud" : "local",
        route: routeFromStatus(status),
    };
}
export function createStatusDrivenDashboardPreferences(status) {
    const llamaControls = isLlamaControls(status?.settings.llamaControls)
        ? status.settings.llamaControls
        : deriveLlamaControls(status?.llamaFirst ?? null);
    return {
        ...createDefaultDashboardPreferences(),
        llamaControls,
        ocrThresholdInput: status ? String(status.settings.ocrReviewThresholdPercent) : "80",
    };
}
export function resolveDashboardPreferences(options) {
    const statusDriven = createStatusDrivenDashboardPreferences(options.status);
    if (!options.stored) {
        return statusDriven;
    }
    return {
        ...statusDriven,
        activeView: options.stored.activeView,
        selectedDocumentIds: options.stored.selectedDocumentIds,
        embeddingIndexing: options.stored.embeddingIndexing,
    };
}
function parseStoredDashboardPreferences(raw) {
    const parsed = JSON.parse(raw);
    if (!isRecord(parsed)) {
        return null;
    }
    const activeView = parsed.activeView;
    const selectedDocumentIds = parsed.selectedDocumentIds;
    if (!isDashboardView(activeView) || !isRecord(selectedDocumentIds)) {
        return null;
    }
    const review = selectedDocumentIds.review;
    const inventory = selectedDocumentIds.inventory;
    if (!isStringOrNull(review) || !isStringOrNull(inventory)) {
        return null;
    }
    const defaults = createDefaultDashboardPreferences();
    const embeddingIndexing = parseEmbeddingIndexingState(parsed.embeddingIndexing);
    return {
        ...defaults,
        activeView,
        selectedDocumentIds: {
            review,
            inventory,
        },
        embeddingIndexing,
    };
}
function persistDashboardPreferences(value) {
    window.localStorage.setItem(STORAGE_KEY, serializeDashboardPreferences(value));
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
}
export function writePayloadForTest(value) {
    return serializeDashboardPreferences(value);
}
export function readDashboardPreferences() {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
            const stored = parseStoredDashboardPreferences(raw);
            if (stored) {
                return stored;
            }
        }
        const legacyRaw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (!legacyRaw) {
            return null;
        }
        const migrated = parseStoredDashboardPreferences(legacyRaw);
        if (!migrated) {
            return null;
        }
        persistDashboardPreferences(migrated);
        return migrated;
    }
    catch {
        return null;
    }
}
export function writeDashboardPreferences(value) {
    if (typeof window === "undefined") {
        return;
    }
    try {
        persistDashboardPreferences(value);
    }
    catch {
        // Silently ignore storage quota or privacy mode failures.
    }
}
