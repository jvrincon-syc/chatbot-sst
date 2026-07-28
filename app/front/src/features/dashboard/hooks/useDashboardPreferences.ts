import { useEffect, useRef, useState } from "react";
import {
  createStatusDrivenDashboardPreferences,
  deriveLlamaControls,
  readDashboardPreferences,
  writeDashboardPreferences,
} from "../dashboardPersistence.js";
import type {
  AppView,
  DashboardPreferences,
  LlamaControls,
  StatusPayload,
} from "../dashboardTypes.js";

export function useDashboardPreferences(status: StatusPayload | null) {
  const [storedPreferences] = useState<DashboardPreferences | null>(() => readDashboardPreferences());
  const [preferences, setPreferences] = useState<DashboardPreferences>(() =>
    storedPreferences ?? createStatusDrivenDashboardPreferences(null),
  );
  const hydratedFromStatusRef = useRef(Boolean(storedPreferences));

  useEffect(() => {
    if (!status || hydratedFromStatusRef.current) {
      return;
    }

    hydratedFromStatusRef.current = true;
    setPreferences((current) => ({
      ...current,
      llamaControls: deriveLlamaControls(status.llamaFirst),
      ocrThresholdInput: String(status.settings.ocrReviewThresholdPercent),
    }));
  }, [status]);

  useEffect(() => {
    writeDashboardPreferences(preferences);
  }, [preferences]);

  const setActiveView = (activeView: AppView) => {
    setPreferences((current) => ({ ...current, activeView }));
  };

  const setLlamaControls = (llamaControls: LlamaControls) => {
    setPreferences((current) => ({ ...current, llamaControls }));
  };

  const setOcrThresholdInput = (ocrThresholdInput: string) => {
    setPreferences((current) => ({ ...current, ocrThresholdInput }));
  };

  const setSelectedDocumentId = (view: Exclude<AppView, "operations">, documentId: string | null) => {
    setPreferences((current) => ({
      ...current,
      selectedDocumentIds: {
        ...current.selectedDocumentIds,
        [view]: documentId,
      },
    }));
  };

  return {
    preferences,
    setActiveView,
    setLlamaControls,
    setOcrThresholdInput,
    setSelectedDocumentId,
  };
}
