import { routeFromStatus, isLlamaRoute } from "../../llamaRoutes.js";
import {
  DEFAULT_LLAMA_CONTROLS,
  createDefaultDashboardPreferences,
} from "./dashboardTypes.js";
import type {
  DashboardPreferences,
  StatusPayload,
} from "./dashboardTypes.js";

const STORAGE_KEY = "chatbot-sst.dashboard.preferences.v1";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isProviderMode(value: unknown): value is "local" | "llama_cloud" {
  return value === "local" || value === "llama_cloud";
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

export function deriveLlamaControls(
  status: StatusPayload["llamaFirst"] | null,
): DashboardPreferences["llamaControls"] {
  if (!status) {
    return DEFAULT_LLAMA_CONTROLS;
  }

  return {
    providerMode: status.cloudEnabled ? "llama_cloud" : "local",
    route: routeFromStatus(status),
  };
}

export function createStatusDrivenDashboardPreferences(
  status: Pick<StatusPayload, "llamaFirst" | "settings"> | null,
): DashboardPreferences {
  return {
    ...createDefaultDashboardPreferences(),
    llamaControls: deriveLlamaControls(status?.llamaFirst ?? null),
    ocrThresholdInput: status ? String(status.settings.ocrReviewThresholdPercent) : "80",
  };
}

export function resolveDashboardPreferences(options: {
  stored: DashboardPreferences | null;
  status: Pick<StatusPayload, "llamaFirst" | "settings"> | null;
}): DashboardPreferences {
  return options.stored ?? createStatusDrivenDashboardPreferences(options.status);
}

export function readDashboardPreferences(): DashboardPreferences | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) {
      return null;
    }

    const activeView = parsed.activeView;
    const selectedDocumentIds = parsed.selectedDocumentIds;
    const llamaControls = parsed.llamaControls;
    const ocrThresholdInput = parsed.ocrThresholdInput;

    if (
      activeView !== "operations" &&
      activeView !== "review" &&
      activeView !== "inventory" &&
      activeView !== "chunking"
    ) {
      return null;
    }
    if (!isRecord(selectedDocumentIds)) {
      return null;
    }
    if (!isRecord(llamaControls) || !isProviderMode(llamaControls.providerMode)) {
      return null;
    }
    if (typeof llamaControls.route !== "string" || !isLlamaRoute(llamaControls.route)) {
      return null;
    }
    if (typeof ocrThresholdInput !== "string") {
      return null;
    }

    const review = selectedDocumentIds.review;
    const inventory = selectedDocumentIds.inventory;

    if (!isStringOrNull(review) || !isStringOrNull(inventory)) {
      return null;
    }

    return {
      activeView,
      selectedDocumentIds: {
        review,
        inventory,
      },
      llamaControls: {
        providerMode: llamaControls.providerMode,
        route: llamaControls.route,
      },
      ocrThresholdInput,
    };
  } catch {
    return null;
  }
}

export function writeDashboardPreferences(value: DashboardPreferences): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Silently ignore storage quota or privacy mode failures.
  }
}
