import { useCallback, useEffect, useState } from "react";
import {
  readDashboardPreferences,
  resolveDashboardPreferences,
  writeDashboardPreferences,
} from "../dashboardPersistence.js";
import type {
  AppView,
  DashboardPreferences,
  EmbeddingIndexingState,
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

  const setActiveView = useCallback((activeView: AppView) => {
    setPreferences((current) => {
      if (current.activeView === activeView) {
        return current;
      }
      return { ...current, activeView };
    });
  }, []);

  const setLlamaControls = useCallback((llamaControls: LlamaControls) => {
    setPreferences((current) => {
      if (
        current.llamaControls.providerMode === llamaControls.providerMode &&
        current.llamaControls.route === llamaControls.route
      ) {
        return current;
      }
      return { ...current, llamaControls };
    });
  }, []);

  const setOcrThresholdInput = useCallback((ocrThresholdInput: string) => {
    setPreferences((current) => {
      if (current.ocrThresholdInput === ocrThresholdInput) {
        return current;
      }
      return { ...current, ocrThresholdInput };
    });
  }, []);

  const setSelectedDocumentId = useCallback(
    (view: DocumentSelectionView, documentId: string | null) => {
      setPreferences((current) => {
        if (current.selectedDocumentIds[view] === documentId) {
          return current;
        }
        return {
          ...current,
          selectedDocumentIds: {
            ...current.selectedDocumentIds,
            [view]: documentId,
          },
        };
      });
    },
    [],
  );

  const setEmbeddingIndexingState = useCallback((patch: Partial<EmbeddingIndexingState>) => {
    setPreferences((current) => {
      const nextEmbeddingIndexing = {
        ...current.embeddingIndexing,
        ...patch,
      };
      const unchanged =
        current.embeddingIndexing.activeStage === nextEmbeddingIndexing.activeStage &&
        current.embeddingIndexing.selectedEmbeddingProfileId ===
          nextEmbeddingIndexing.selectedEmbeddingProfileId &&
        current.embeddingIndexing.selectedChunkBundleId ===
          nextEmbeddingIndexing.selectedChunkBundleId &&
        current.embeddingIndexing.activeEmbeddingRunId ===
          nextEmbeddingIndexing.activeEmbeddingRunId &&
        current.embeddingIndexing.selectedEmbeddingBundleId ===
          nextEmbeddingIndexing.selectedEmbeddingBundleId &&
        current.embeddingIndexing.activeIndexingRunId ===
          nextEmbeddingIndexing.activeIndexingRunId &&
        current.embeddingIndexing.activeActivationRunId ===
          nextEmbeddingIndexing.activeActivationRunId &&
        current.embeddingIndexing.selectedRetrievalProfileId ===
          nextEmbeddingIndexing.selectedRetrievalProfileId;
      if (unchanged) {
        return current;
      }
      return {
        ...current,
        embeddingIndexing: nextEmbeddingIndexing,
      };
    });
  }, []);

  const setEmbeddingIndexingActiveStage = useCallback(
    (activeStage: EmbeddingIndexingState["activeStage"]) => {
      setEmbeddingIndexingState({ activeStage });
    },
    [setEmbeddingIndexingState],
  );

  return {
    preferences,
    setActiveView,
    setLlamaControls,
    setOcrThresholdInput,
    setSelectedDocumentId,
    setEmbeddingIndexingState,
    setEmbeddingIndexingActiveStage,
  };
}
