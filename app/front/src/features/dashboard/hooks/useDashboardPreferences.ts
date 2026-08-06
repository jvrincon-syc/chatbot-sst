import { useEffect, useState } from "react";
import {
  readDashboardPreferences,
  resolveDashboardPreferences,
  writeDashboardPreferences,
} from "../dashboardPersistence.js";
import type {
  AppView,
  DashboardPreferences,
  EmbeddingIndexingStage,
  LlamaControls,
  StatusPayload,
  DocumentSelectionView,
} from "../dashboardTypes.js";

export function useDashboardPreferences(status: StatusPayload | null) {
  const [preferences, setPreferences] = useState<DashboardPreferences>(() =>
    resolveDashboardPreferences({
      stored: readDashboardPreferences(),
      status: null,
    }),
  );

  useEffect(() => {
    if (!status) {
      return;
    }

    setPreferences((current) =>
      resolveDashboardPreferences({
        stored: current,
        status,
      }),
    );
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

  const setSelectedDocumentId = (view: DocumentSelectionView, documentId: string | null) => {
    setPreferences((current) => ({
      ...current,
      selectedDocumentIds: {
        ...current.selectedDocumentIds,
        [view]: documentId,
      },
    }));
  };

  const setEmbeddingIndexingActiveStage = (activeStage: EmbeddingIndexingStage) => {
    setPreferences((current) => ({
      ...current,
      embeddingIndexing: {
        activeStage,
      },
    }));
  };

  return {
    preferences,
    setActiveView,
    setLlamaControls,
    setOcrThresholdInput,
    setSelectedDocumentId,
    setEmbeddingIndexingActiveStage,
  };
}
