import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEmbeddingRun,
  loadChunkBundles,
  loadEmbeddingBundle,
  loadEmbeddingBundleChunks,
  loadEmbeddingBundleValidation,
  loadEmbeddingIndexingReadiness,
  loadEmbeddingProfiles,
} from "../embedding/embeddingApi.js";
import { embeddingProfileSelectable, embeddingRunProducedBundleId } from "../embedding/embeddingState.js";
import { useEmbeddingRunPolling } from "../embedding/hooks/useEmbeddingRunPolling.js";
import type {
  EmbeddingBundleChunk,
  EmbeddingBundleSummary,
  EmbeddingBundleValidation,
  EmbeddingChunkBundleListItem,
  EmbeddingIndexingReadiness,
  EmbeddingProfile,
} from "../embedding/embeddingTypes.js";
import {
  activateIndexingRun,
  createIndexingRun,
  loadIndexingOverview,
  loadIndexingRetrievalReadiness,
  loadIndexingRunDocuments,
  loadIndexingRunErrors,
} from "../indexing/indexingApi.js";
import { useIndexingRunPolling } from "../indexing/hooks/useIndexingRunPolling.js";
import type {
  ActivationResult,
  IndexingRetrievalReadiness,
  IndexingRunDocument,
  IndexingRunError,
} from "../indexing/indexingTypes.js";
import {
  loadRetrievalProfileStatus,
  loadRetrievalProfiles,
  validateRetrievalProfile,
} from "../retrieval/retrievalApi.js";
import type {
  RetrievalProfile,
  RetrievalProfileStatus,
  RetrievalValidationResult,
} from "../retrieval/retrievalTypes.js";
import { mapPipelineError } from "./shared/errorMapping.js";
import type { PaginatedResponse } from "./shared/apiTypes.js";
import type { EmbeddingIndexingState } from "../dashboard/dashboardTypes.js";

function errorMessage(caught: unknown): string {
  return mapPipelineError(caught).message;
}

// Orchestrates the embedding -> indexing -> activation -> retrieval flow. It owns
// the working ids that need to survive reloads and exposes typed slices the
// workspace hands to each feature panel. Keeping this out of the view component
// prevents the workspace from becoming a monolith.
type UseEmbeddingIndexingPipelineOptions = {
  persistedState: EmbeddingIndexingState;
  onPersistedStateChange: (patch: Partial<EmbeddingIndexingState>) => void;
};

export function useEmbeddingIndexingPipeline({
  persistedState,
  onPersistedStateChange,
}: UseEmbeddingIndexingPipelineOptions) {
  const persistState = useCallback(
    (patch: Partial<EmbeddingIndexingState>) => {
      onPersistedStateChange(patch);
    },
    [onPersistedStateChange],
  );
  // --- Embedding catalog ---
  const [profiles, setProfiles] = useState<EmbeddingProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);

  const [chunkBundles, setChunkBundles] = useState<EmbeddingChunkBundleListItem[]>([]);
  const [chunkBundlesLoading, setChunkBundlesLoading] = useState(true);
  const [chunkBundlesError, setChunkBundlesError] = useState<string | null>(null);
  const [selectedChunkBundleId, setSelectedChunkBundleId] = useState<string | null>(
    persistedState.selectedChunkBundleId,
  );

  // --- Embedding run ---
  const [embeddingRunId, setEmbeddingRunId] = useState<string | null>(
    persistedState.activeEmbeddingRunId,
  );
  const [embeddingLaunchBusy, setEmbeddingLaunchBusy] = useState(false);
  const [embeddingLaunchError, setEmbeddingLaunchError] = useState<string | null>(null);
  const embeddingPolling = useEmbeddingRunPolling(embeddingRunId);
  const embeddingRun = embeddingPolling.run;

  // --- Embedding bundle inspection ---
  const [embeddingBundle, setEmbeddingBundle] = useState<EmbeddingBundleSummary | null>(null);
  const [embeddingBundleLoading, setEmbeddingBundleLoading] = useState(false);
  const [embeddingBundleError, setEmbeddingBundleError] = useState<string | null>(null);
  const [bundleChunks, setBundleChunks] = useState<PaginatedResponse<EmbeddingBundleChunk> | null>(null);
  const [bundleChunksLoading, setBundleChunksLoading] = useState(false);
  const [bundleValidation, setBundleValidation] = useState<EmbeddingBundleValidation | null>(null);
  const [bundleReadiness, setBundleReadiness] = useState<EmbeddingIndexingReadiness | null>(null);
  const [selectedEmbeddingBundleId, setSelectedEmbeddingBundleId] = useState<string | null>(
    persistedState.selectedEmbeddingBundleId,
  );

  // --- Indexing ---
  const [bundleFirstEnabled, setBundleFirstEnabled] = useState(true);
  const [indexingRunId, setIndexingRunId] = useState<string | null>(
    persistedState.activeIndexingRunId,
  );
  const [indexingLaunchBusy, setIndexingLaunchBusy] = useState(false);
  const [indexingLaunchError, setIndexingLaunchError] = useState<string | null>(null);
  const indexingPolling = useIndexingRunPolling(indexingRunId);
  const indexingRun = indexingPolling.run;
  const [indexingDocuments, setIndexingDocuments] =
    useState<PaginatedResponse<IndexingRunDocument> | null>(null);
  const [indexingDocumentsLoading, setIndexingDocumentsLoading] = useState(false);
  const [indexingDocumentsError, setIndexingDocumentsError] = useState<string | null>(null);
  const [indexingErrors, setIndexingErrors] =
    useState<PaginatedResponse<IndexingRunError> | null>(null);
  const [indexingErrorsLoading, setIndexingErrorsLoading] = useState(false);
  const [indexingErrorsError, setIndexingErrorsError] = useState<string | null>(null);

  // --- Activation ---
  const [lexicalFallbackPolicy, setLexicalFallbackPolicy] = useState(
    "allowed_when_vector_unavailable",
  );
  const [activationRunId, setActivationRunId] = useState<string | null>(
    persistedState.activeActivationRunId,
  );
  const [activationBusy, setActivationBusy] = useState(false);
  const [activationError, setActivationError] = useState<string | null>(null);
  const [activationResult, setActivationResult] = useState<ActivationResult | null>(null);
  const [indexingReadiness, setIndexingReadiness] =
    useState<IndexingRetrievalReadiness | null>(null);

  // --- Retrieval ---
  const [retrievalProfileId, setRetrievalProfileId] = useState<string | null>(
    persistedState.selectedRetrievalProfileId,
  );
  const [retrievalProfiles, setRetrievalProfiles] = useState<RetrievalProfile[]>([]);
  const [retrievalProfilesLoading, setRetrievalProfilesLoading] = useState(true);
  const [retrievalProfilesError, setRetrievalProfilesError] = useState<string | null>(null);
  const [retrievalStatus, setRetrievalStatus] = useState<RetrievalProfileStatus | null>(null);
  const [retrievalStatusLoading, setRetrievalStatusLoading] = useState(false);
  const [retrievalStatusError, setRetrievalStatusError] = useState<string | null>(null);
  const [retrievalValidationBusy, setRetrievalValidationBusy] = useState(false);
  const [retrievalValidationError, setRetrievalValidationError] = useState<string | null>(null);
  const [retrievalValidationResult, setRetrievalValidationResult] =
    useState<RetrievalValidationResult | null>(null);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.profileId === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );

  const selectChunkBundle = useCallback(
    (chunkBundleId: string | null) => {
      setSelectedChunkBundleId(chunkBundleId);
      persistState({ selectedChunkBundleId: chunkBundleId });
    },
    [persistState],
  );

  const selectRetrievalProfile = useCallback(
    (selectedId: string | null) => {
      setRetrievalProfileId(selectedId);
      persistState({ selectedRetrievalProfileId: selectedId });
    },
    [persistState],
  );

  const refreshCatalog = useCallback(async () => {
    setProfilesLoading(true);
    setChunkBundlesLoading(true);
    setProfilesError(null);
    setChunkBundlesError(null);
    try {
      const [profilePage, overview] = await Promise.all([
        loadEmbeddingProfiles(),
        loadIndexingOverview().catch(() => null),
      ]);
      setProfiles(profilePage.items);
      setSelectedProfileId((current) => {
        if (current && profilePage.items.some((profile) => profile.profileId === current)) {
          return current;
        }
        const firstSelectable = profilePage.items.find(embeddingProfileSelectable);
        return firstSelectable?.profileId ?? current ?? null;
      });
      if (overview) {
        setBundleFirstEnabled(overview.bundleFirstEnabled);
      }
    } catch (caught) {
      setProfilesError(errorMessage(caught));
    } finally {
      setProfilesLoading(false);
    }

    try {
      const bundlePage = await loadChunkBundles();
      setChunkBundles(bundlePage.items);
    } catch (caught) {
      setChunkBundlesError(errorMessage(caught));
    } finally {
      setChunkBundlesLoading(false);
    }

    setRetrievalProfilesLoading(true);
    setRetrievalProfilesError(null);
    try {
      const retrievalPage = await loadRetrievalProfiles();
      setRetrievalProfiles(retrievalPage.items);
      const nextRetrievalProfileId =
        retrievalProfileId &&
        retrievalPage.items.some(
          (profile) => profile.retrievalProfileId === retrievalProfileId,
        )
          ? retrievalProfileId
          : retrievalPage.items.find((profile) => profile.active)?.retrievalProfileId ??
            retrievalProfileId ??
            null;
      setRetrievalProfileId(nextRetrievalProfileId);
      if (nextRetrievalProfileId !== retrievalProfileId) {
        persistState({ selectedRetrievalProfileId: nextRetrievalProfileId });
      }
    } catch (caught) {
      setRetrievalProfilesError(errorMessage(caught));
    } finally {
      setRetrievalProfilesLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  const createEmbedding = useCallback(async () => {
    if (!selectedChunkBundleId || !selectedProfileId) return;
    setEmbeddingLaunchBusy(true);
    setEmbeddingLaunchError(null);
    try {
      const run = await createEmbeddingRun(
        {
          chunkBundleId: selectedChunkBundleId,
          profileId: selectedProfileId,
        },
        {},
      );
      setEmbeddingRunId(run.embeddingRunId);
      persistState({
        selectedChunkBundleId,
        activeEmbeddingRunId: run.embeddingRunId,
        activeStage: "embedding",
      });
    } catch (caught) {
      setEmbeddingLaunchError(errorMessage(caught));
    } finally {
      setEmbeddingLaunchBusy(false);
    }
  }, [persistState, selectedChunkBundleId, selectedProfileId]);

  // When the embedding run completes, pivot to its produced embedding bundle and
  // load bundle-level inspection (never run-documents/run-items).
  const producedBundleId = embeddingRun ? embeddingRunProducedBundleId(embeddingRun) : null;
  const resolvedEmbeddingBundleId = selectedEmbeddingBundleId ?? producedBundleId;
  useEffect(() => {
    if (!resolvedEmbeddingBundleId) {
      return;
    }
    let cancelled = false;
    setEmbeddingBundleLoading(true);
    setBundleChunksLoading(true);
    setEmbeddingBundleError(null);
    void (async () => {
      try {
        const [bundle, chunks, validation, readiness] = await Promise.all([
          loadEmbeddingBundle(resolvedEmbeddingBundleId),
          loadEmbeddingBundleChunks(resolvedEmbeddingBundleId, { page: 1 }),
          loadEmbeddingBundleValidation(resolvedEmbeddingBundleId).catch(() => null),
          loadEmbeddingIndexingReadiness(resolvedEmbeddingBundleId).catch(() => null),
        ]);
        if (cancelled) return;
        setEmbeddingBundle(bundle);
        setBundleChunks(chunks);
        setBundleValidation(validation);
        setBundleReadiness(readiness);
      } catch (caught) {
        if (cancelled) return;
        setEmbeddingBundleError(errorMessage(caught));
      } finally {
        if (!cancelled) {
          setEmbeddingBundleLoading(false);
          setBundleChunksLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resolvedEmbeddingBundleId]);

  useEffect(() => {
    if (!producedBundleId) {
      return;
    }
    setSelectedEmbeddingBundleId(producedBundleId);
    persistState({
      selectedEmbeddingBundleId: producedBundleId,
      activeEmbeddingRunId: embeddingRunId,
    });
  }, [embeddingRunId, persistState, producedBundleId]);

  const createIndexing = useCallback(async () => {
    if (!resolvedEmbeddingBundleId) return;
    setIndexingLaunchBusy(true);
    setIndexingLaunchError(null);
    try {
      const run = await createIndexingRun({ embeddingBundleId: resolvedEmbeddingBundleId }, {});
      setIndexingRunId(run.runId);
      persistState({
        selectedEmbeddingBundleId: resolvedEmbeddingBundleId,
        activeIndexingRunId: run.runId,
        activeStage: "indexing",
      });
    } catch (caught) {
      setIndexingLaunchError(errorMessage(caught));
    } finally {
      setIndexingLaunchBusy(false);
    }
  }, [persistState, resolvedEmbeddingBundleId]);

  // Load indexing run detail (documents, errors, retrieval readiness) whenever a
  // fresh indexing run snapshot arrives.
  const indexingRunStatus = indexingRun?.status ?? null;
  useEffect(() => {
    if (!indexingRunId) {
      return;
    }
    let cancelled = false;
    setIndexingDocumentsLoading(true);
    setIndexingErrorsLoading(true);
    void (async () => {
      try {
        const [documents, errors, readiness] = await Promise.all([
          loadIndexingRunDocuments(indexingRunId, { page: 1 }),
          loadIndexingRunErrors(indexingRunId, { page: 1 }).catch(() => null),
          loadIndexingRetrievalReadiness(indexingRunId).catch(() => null),
        ]);
        if (cancelled) return;
        setIndexingDocuments(documents);
        if (errors) setIndexingErrors(errors);
        setIndexingReadiness(readiness);
      } catch (caught) {
        if (cancelled) return;
        setIndexingDocumentsError(errorMessage(caught));
        setIndexingErrorsError(errorMessage(caught));
      } finally {
        if (!cancelled) {
          setIndexingDocumentsLoading(false);
          setIndexingErrorsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [indexingRunId, indexingRunStatus]);

  const activate = useCallback(async () => {
    if (!indexingRunId) return;
    setActivationBusy(true);
    setActivationError(null);
    setActivationRunId(indexingRunId);
    persistState({
      activeActivationRunId: indexingRunId,
      activeStage: "activation",
    });
    try {
      const result = await activateIndexingRun({
        runId: indexingRunId,
        lexicalFallbackPolicy,
      });
      setActivationResult(result);
      if (result.retrievalProfileId) {
        setRetrievalProfileId(result.retrievalProfileId);
        persistState({
          selectedRetrievalProfileId: result.retrievalProfileId,
          activeActivationRunId: indexingRunId,
          activeStage: "retrieval",
        });
      }
    } catch (caught) {
      setActivationError(errorMessage(caught));
    } finally {
      setActivationBusy(false);
    }
  }, [indexingRunId, lexicalFallbackPolicy, persistState]);

  const refreshRetrievalStatus = useCallback(async () => {
    if (!retrievalProfileId) return;
    setRetrievalStatusLoading(true);
    setRetrievalStatusError(null);
    try {
      const status = await loadRetrievalProfileStatus(retrievalProfileId);
      setRetrievalStatus(status);
    } catch (caught) {
      setRetrievalStatusError(errorMessage(caught));
    } finally {
      setRetrievalStatusLoading(false);
    }
  }, [retrievalProfileId]);

  useEffect(() => {
    void refreshRetrievalStatus();
  }, [refreshRetrievalStatus]);

  const validateRetrieval = useCallback(async () => {
    if (!retrievalProfileId) return;
    setRetrievalValidationBusy(true);
    setRetrievalValidationError(null);
    try {
      const result = await validateRetrievalProfile(retrievalProfileId);
      setRetrievalValidationResult(result);
      await refreshRetrievalStatus();
    } catch (caught) {
      setRetrievalValidationError(errorMessage(caught));
    } finally {
      setRetrievalValidationBusy(false);
    }
  }, [retrievalProfileId, refreshRetrievalStatus]);

  return {
    embedding: {
      profiles,
      profilesLoading,
      profilesError,
      selectedProfileId,
      selectProfile: setSelectedProfileId,
      selectedProfile,
      chunkBundles,
      chunkBundlesLoading,
      chunkBundlesError,
      selectedChunkBundleId,
      selectChunkBundle,
      run: embeddingRun,
      polling: embeddingPolling.polling,
      launchBusy: embeddingLaunchBusy,
      launchError: embeddingLaunchError,
      createRun: createEmbedding,
      bundle: embeddingBundle,
      bundleLoading: embeddingBundleLoading,
      bundleError: embeddingBundleError,
      bundleChunks,
      bundleChunksLoading,
      bundleValidation,
      bundleReadiness,
    },
    indexing: {
      embeddingBundleId: resolvedEmbeddingBundleId,
      embeddingBundleReady: bundleReadiness?.status === "ready",
      bundleFirstEnabled,
      run: indexingRun,
      polling: indexingPolling.polling,
      launchBusy: indexingLaunchBusy,
      launchError: indexingLaunchError,
      createRun: createIndexing,
      documents: indexingDocuments,
      documentsLoading: indexingDocumentsLoading,
      documentsError: indexingDocumentsError,
      errors: indexingErrors,
      errorsLoading: indexingErrorsLoading,
      errorsError: indexingErrorsError,
    },
    activation: {
      run: indexingRun,
      runId: activationRunId,
      readiness: indexingReadiness,
      lexicalFallbackPolicy,
      setLexicalFallbackPolicy,
      busy: activationBusy,
      error: activationError,
      result: activationResult,
      activate,
    },
    retrieval: {
      retrievalProfileId,
      profiles: retrievalProfiles,
      profilesLoading: retrievalProfilesLoading,
      profilesError: retrievalProfilesError,
      selectRetrievalProfile,
      status: retrievalStatus,
      statusLoading: retrievalStatusLoading,
      statusError: retrievalStatusError,
      validationBusy: retrievalValidationBusy,
      validationError: retrievalValidationError,
      validationResult: retrievalValidationResult,
      validate: validateRetrieval,
    },
    refreshCatalog,
    refreshing: profilesLoading || chunkBundlesLoading,
  };
}

export type EmbeddingIndexingPipeline = ReturnType<typeof useEmbeddingIndexingPipeline>;
