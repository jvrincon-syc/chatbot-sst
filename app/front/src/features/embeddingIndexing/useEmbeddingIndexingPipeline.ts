import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEmbeddingRun,
  loadChunkBundleSummary,
  loadChunkBundles,
  loadEmbeddingBundle,
  loadEmbeddingBundleChunks,
  loadEmbeddingBundleValidation,
  loadEmbeddingIndexingReadiness,
  loadEmbeddingRun,
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
  loadIndexingRun,
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
  searchRetrieval,
  validateRetrievalProfile,
} from "../retrieval/retrievalApi.js";
import type {
  RetrievalSearchResult,
  RetrievalProfile,
  RetrievalProfileStatus,
  RetrievalValidationResult,
} from "../retrieval/retrievalTypes.js";
import { mapPipelineError } from "./shared/errorMapping.js";
import type { PaginatedResponse } from "./shared/apiTypes.js";
import type { EmbeddingIndexingState } from "../dashboard/dashboardTypes.js";
import { shouldAdvanceToIndexing } from "./shared/pipelineFlow.js";
import {
  clearMissingPipelineResource,
  type CorpusBatchProgress,
} from "./shared/pipelineState.js";

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

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "blocked", "cancelled"]);
const CORPUS_PAGE_SIZE = 100;
const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 300;

function sleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, delayMs);
  });
}

async function loadAllPages<T>(
  loader: (options: { page: number; pageSize: number }) => Promise<PaginatedResponse<T>>,
): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  while (true) {
    const response = await loader({ page, pageSize: CORPUS_PAGE_SIZE });
    items.push(...response.items);
    if (response.totalPages <= page || response.totalPages === 0) {
      break;
    }
    page += 1;
  }
  return items;
}

function summarizeBatchFailures(label: string, failures: string[]): string | null {
  if (failures.length === 0) {
    return null;
  }
  const preview = failures.slice(0, 3).join(" | ");
  const suffix = failures.length > 3 ? ` | +${failures.length - 3} mas` : "";
  return `${label}: ${preview}${suffix}`;
}

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
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(
    persistedState.selectedEmbeddingProfileId,
  );

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
  const [embeddingCorpusBusy, setEmbeddingCorpusBusy] = useState(false);
  const [embeddingCorpusError, setEmbeddingCorpusError] = useState<string | null>(null);
  const [embeddingCorpusProgress, setEmbeddingCorpusProgress] =
    useState<CorpusBatchProgress | null>(null);
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
  const [indexingCorpusBusy, setIndexingCorpusBusy] = useState(false);
  const [indexingCorpusError, setIndexingCorpusError] = useState<string | null>(null);
  const [indexingCorpusProgress, setIndexingCorpusProgress] =
    useState<CorpusBatchProgress | null>(null);
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
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalTopK, setRetrievalTopK] = useState(5);
  const [retrievalSearchBusy, setRetrievalSearchBusy] = useState(false);
  const [retrievalSearchError, setRetrievalSearchError] = useState<string | null>(null);
  const [retrievalSearchResult, setRetrievalSearchResult] =
    useState<RetrievalSearchResult | null>(null);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.profileId === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );

  const selectProfile = useCallback(
    (profileId: string | null) => {
      setSelectedProfileId(profileId);
      persistState({ selectedEmbeddingProfileId: profileId });
    },
    [persistState],
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
        const nextProfileId =
          firstSelectable?.profileId ?? profilePage.items[0]?.profileId ?? current ?? null;
        if (nextProfileId !== current) {
          persistState({ selectedEmbeddingProfileId: nextProfileId });
        }
        return nextProfileId;
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
      setSelectedChunkBundleId((current) => {
        if (current && bundlePage.items.some((bundle) => bundle.chunkBundleId === current)) {
          return current;
        }
        const nextChunkBundleId = bundlePage.items[0]?.chunkBundleId ?? current ?? null;
        if (nextChunkBundleId !== current) {
          persistState({ selectedChunkBundleId: nextChunkBundleId });
        }
        return nextChunkBundleId;
      });
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
      setRetrievalProfileId((current) => {
        const currentIsAvailable =
          current &&
          retrievalPage.items.some((profile) => profile.retrievalProfileId === current);
        const nextRetrievalProfileId = currentIsAvailable
          ? current
          : retrievalPage.items.find((profile) => profile.active)?.retrievalProfileId ??
            current ??
            null;
        if (nextRetrievalProfileId !== current) {
          persistState({ selectedRetrievalProfileId: nextRetrievalProfileId });
        }
        return nextRetrievalProfileId;
      });
    } catch (caught) {
      setRetrievalProfilesError(errorMessage(caught));
    } finally {
      setRetrievalProfilesLoading(false);
    }
  }, [persistState]);

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

  const waitForEmbeddingRun = useCallback(async (runId: string) => {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
      const run = await loadEmbeddingRun(runId);
      if (TERMINAL_RUN_STATUSES.has(run.status)) {
        return run;
      }
      await sleep(POLL_INTERVAL_MS);
    }
    throw new Error(`El run de embedding ${runId} no alcanzo un estado terminal.`);
  }, []);

  const createCorpusEmbedding = useCallback(async () => {
    if (!selectedProfileId) {
      return;
    }
    setEmbeddingCorpusBusy(true);
    setEmbeddingCorpusError(null);
    try {
      const allChunkBundles = await loadAllPages(loadChunkBundles);
      setEmbeddingCorpusProgress({
        total: allChunkBundles.length,
        completed: 0,
        succeeded: 0,
        failed: 0,
        currentLabel: null,
      });
      const failures: string[] = [];
      let succeeded = 0;
      let lastRunId: string | null = null;
      let lastBundleId: string | null = null;
      for (const [index, chunkBundle] of allChunkBundles.entries()) {
        setEmbeddingCorpusProgress({
          total: allChunkBundles.length,
          completed: index,
          succeeded,
          failed: failures.length,
          currentLabel: chunkBundle.chunkBundleId,
        });
        try {
          setSelectedChunkBundleId(chunkBundle.chunkBundleId);
          const run = await createEmbeddingRun(
            {
              chunkBundleId: chunkBundle.chunkBundleId,
              profileId: selectedProfileId,
            },
            {},
          );
          setEmbeddingRunId(run.embeddingRunId);
          lastRunId = run.embeddingRunId;
          persistState({
            selectedChunkBundleId: chunkBundle.chunkBundleId,
            activeEmbeddingRunId: run.embeddingRunId,
            activeStage: "embedding",
          });
          const completedRun = await waitForEmbeddingRun(run.embeddingRunId);
          setEmbeddingRunId(completedRun.embeddingRunId);
          if (
            completedRun.status !== "completed" ||
            completedRun.producedEmbeddingBundleId === null
          ) {
            failures.push(
              `${chunkBundle.chunkBundleId}: ${completedRun.errorSummary ?? completedRun.status}`,
            );
          } else {
            succeeded += 1;
            lastBundleId = completedRun.producedEmbeddingBundleId;
            setSelectedEmbeddingBundleId(completedRun.producedEmbeddingBundleId);
            persistState({
              selectedEmbeddingBundleId: completedRun.producedEmbeddingBundleId,
              activeEmbeddingRunId: completedRun.embeddingRunId,
            });
          }
        } catch (caught) {
          failures.push(`${chunkBundle.chunkBundleId}: ${errorMessage(caught)}`);
        }
        setEmbeddingCorpusProgress({
          total: allChunkBundles.length,
          completed: index + 1,
          succeeded,
          failed: failures.length,
          currentLabel: chunkBundle.chunkBundleId,
        });
      }
      if (lastRunId) {
        setEmbeddingRunId(lastRunId);
      }
      if (lastBundleId) {
        setSelectedEmbeddingBundleId(lastBundleId);
        persistState({
          selectedEmbeddingBundleId: lastBundleId,
          activeEmbeddingRunId: lastRunId,
        });
      }
      setEmbeddingCorpusError(
        summarizeBatchFailures("Fallaron algunos embeddings del corpus", failures),
      );
    } catch (caught) {
      setEmbeddingCorpusError(errorMessage(caught));
    } finally {
      setEmbeddingCorpusBusy(false);
      await refreshCatalog();
    }
  }, [persistState, refreshCatalog, selectedProfileId, waitForEmbeddingRun]);

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
        const error = mapPipelineError(caught);
        if (error.code === "EMBEDDING_BUNDLE_NOT_FOUND") {
          const patch = clearMissingPipelineResource(persistedState, "embeddingBundle");
          setSelectedEmbeddingBundleId(null);
          setIndexingRunId(null);
          setActivationRunId(null);
          setRetrievalProfileId(null);
          setEmbeddingBundle(null);
          setBundleChunks(null);
          setBundleValidation(null);
          setBundleReadiness(null);
          persistState(patch);
          return;
        }
        setEmbeddingBundleError(error.message);
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
    if (embeddingPolling.error?.code !== "EMBEDDING_RUN_NOT_FOUND") {
      return;
    }
    const patch = clearMissingPipelineResource(persistedState, "embeddingRun");
    setEmbeddingRunId(null);
    persistState(patch);
  }, [embeddingPolling.error?.code, persistState, persistedState]);

  useEffect(() => {
    if (!producedBundleId) {
      return;
    }
    const nextStage = shouldAdvanceToIndexing({
      activeStage: persistedState.activeStage,
      producedBundleId,
      indexingRunId,
      embeddingCorpusBusy,
    })
      ? "indexing"
      : persistedState.activeStage;
    setSelectedEmbeddingBundleId(producedBundleId);
    persistState({
      selectedEmbeddingBundleId: producedBundleId,
      activeEmbeddingRunId: embeddingRunId,
      activeStage: nextStage,
    });
  }, [
    embeddingCorpusBusy,
    embeddingRunId,
    indexingRunId,
    persistState,
    persistedState.activeStage,
    producedBundleId,
  ]);

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

  const waitForIndexingRun = useCallback(async (runId: string) => {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
      const run = await loadIndexingRun(runId);
      if (TERMINAL_RUN_STATUSES.has(run.status)) {
        return run;
      }
      await sleep(POLL_INTERVAL_MS);
    }
    throw new Error(`El run de indexing ${runId} no alcanzo un estado terminal.`);
  }, []);

  const createCorpusIndexing = useCallback(async () => {
    if (!selectedProfileId || !bundleFirstEnabled) {
      return;
    }
    setIndexingCorpusBusy(true);
    setIndexingCorpusError(null);
    try {
      const allChunkBundles = await loadAllPages(loadChunkBundles);
      const candidates: Array<{ chunkBundleId: string; embeddingBundleId: string }> = [];
      const preparationFailures: string[] = [];
      for (const chunkBundle of allChunkBundles) {
        try {
          const summary = await loadChunkBundleSummary(chunkBundle.chunkBundleId);
          const bundleDetails = await Promise.all(
            summary.embeddingBundleIds.map((embeddingBundleId) =>
              loadEmbeddingBundle(embeddingBundleId),
            ),
          );
          const selectedBundle = bundleDetails
            .filter(
              (bundle) =>
                bundle.embeddingProfileId === selectedProfileId &&
                bundle.status === "sealed" &&
                bundle.validationStatus === "passed" &&
                bundle.readinessStatus === "ready",
            )
            .sort((left, right) => {
              const leftTime = Date.parse(left.sealedAt ?? "") || 0;
              const rightTime = Date.parse(right.sealedAt ?? "") || 0;
              return rightTime - leftTime;
            })[0];
          if (!selectedBundle) {
            preparationFailures.push(
              `${chunkBundle.chunkBundleId}: no tiene embedding listo para ${selectedProfileId}`,
            );
            continue;
          }
          candidates.push({
            chunkBundleId: chunkBundle.chunkBundleId,
            embeddingBundleId: selectedBundle.embeddingBundleId,
          });
        } catch (caught) {
          preparationFailures.push(`${chunkBundle.chunkBundleId}: ${errorMessage(caught)}`);
        }
      }
      setIndexingCorpusProgress({
        total: allChunkBundles.length,
        completed: preparationFailures.length,
        succeeded: 0,
        failed: preparationFailures.length,
        currentLabel: null,
      });
      const failures = [...preparationFailures];
      let succeeded = 0;
      let lastActivation: ActivationResult | null = null;
      for (const [index, candidate] of candidates.entries()) {
        setIndexingCorpusProgress({
          total: allChunkBundles.length,
          completed: preparationFailures.length + index,
          succeeded,
          failed: failures.length,
          currentLabel: candidate.chunkBundleId,
        });
        try {
          const run = await createIndexingRun(
            { embeddingBundleId: candidate.embeddingBundleId },
            {},
          );
          setIndexingRunId(run.runId);
          persistState({
            selectedEmbeddingBundleId: candidate.embeddingBundleId,
            activeIndexingRunId: run.runId,
            activeStage: "indexing",
          });
          const completedRun = await waitForIndexingRun(run.runId);
          setIndexingRunId(completedRun.runId);
          if (completedRun.status !== "completed") {
            failures.push(`${candidate.chunkBundleId}: ${completedRun.status}`);
          } else {
            const activation = await activateIndexingRun({
              runId: completedRun.runId,
              lexicalFallbackPolicy,
            });
            lastActivation = activation;
            succeeded += 1;
            setActivationRunId(completedRun.runId);
            setActivationResult(activation);
            if (activation.retrievalProfileId) {
              setRetrievalProfileId(activation.retrievalProfileId);
              persistState({
                selectedRetrievalProfileId: activation.retrievalProfileId,
                activeActivationRunId: completedRun.runId,
                activeStage: "retrieval",
              });
            }
          }
        } catch (caught) {
          failures.push(`${candidate.chunkBundleId}: ${errorMessage(caught)}`);
        }
        setIndexingCorpusProgress({
          total: allChunkBundles.length,
          completed: preparationFailures.length + index + 1,
          succeeded,
          failed: failures.length,
          currentLabel: candidate.chunkBundleId,
        });
      }
      if (lastActivation?.retrievalProfileId) {
        const status = await loadRetrievalProfileStatus(lastActivation.retrievalProfileId);
        setRetrievalStatus(status);
      }
      setIndexingCorpusError(
        summarizeBatchFailures("Fallaron algunos indexings del corpus", failures),
      );
    } catch (caught) {
      setIndexingCorpusError(errorMessage(caught));
    } finally {
      setIndexingCorpusBusy(false);
      await refreshCatalog();
    }
  }, [
    bundleFirstEnabled,
    lexicalFallbackPolicy,
    persistState,
    refreshCatalog,
    selectedProfileId,
    waitForIndexingRun,
  ]);

  useEffect(() => {
    if (indexingPolling.error?.code !== "INDEXING_RUN_NOT_FOUND") {
      return;
    }
    const patch = clearMissingPipelineResource(persistedState, "indexingRun");
    setIndexingRunId(null);
    setActivationRunId(null);
    setIndexingDocuments(null);
    setIndexingErrors(null);
    setIndexingReadiness(null);
    persistState(patch);
  }, [indexingPolling.error?.code, persistState, persistedState]);

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
      const error = mapPipelineError(caught);
      if (error.code === "RETRIEVAL_PROFILE_NOT_FOUND") {
        const patch = clearMissingPipelineResource(persistedState, "retrievalProfile");
        setRetrievalProfileId(null);
        setRetrievalStatus(null);
        setRetrievalValidationResult(null);
        setRetrievalSearchResult(null);
        persistState(patch);
        return;
      }
      setRetrievalStatusError(error.message);
    } finally {
      setRetrievalStatusLoading(false);
    }
  }, [persistState, persistedState, retrievalProfileId]);

  useEffect(() => {
    void refreshRetrievalStatus();
  }, [refreshRetrievalStatus]);

  useEffect(() => {
    setRetrievalSearchError(null);
    setRetrievalSearchResult(null);
  }, [retrievalProfileId]);

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

  const runRetrievalSearch = useCallback(async () => {
    if (!retrievalProfileId) {
      return;
    }
    const trimmedQuery = retrievalQuery.trim();
    if (!trimmedQuery) {
      setRetrievalSearchError("Escribe una consulta antes de buscar evidencia.");
      return;
    }
    setRetrievalSearchBusy(true);
    setRetrievalSearchError(null);
    try {
      const result = await searchRetrieval({
        retrievalProfileId,
        query: trimmedQuery,
        topK: retrievalTopK,
      });
      setRetrievalSearchResult(result);
    } catch (caught) {
      setRetrievalSearchError(errorMessage(caught));
    } finally {
      setRetrievalSearchBusy(false);
    }
  }, [retrievalProfileId, retrievalQuery, retrievalTopK]);

  return {
    embedding: {
      profiles,
      profilesLoading,
      profilesError,
      selectedProfileId,
      selectProfile,
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
      corpusLaunchBusy: embeddingCorpusBusy,
      corpusLaunchError: embeddingCorpusError,
      corpusProgress: embeddingCorpusProgress,
      createCorpusRun: createCorpusEmbedding,
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
      corpusLaunchBusy: indexingCorpusBusy,
      corpusLaunchError: indexingCorpusError,
      corpusProgress: indexingCorpusProgress,
      createCorpusRun: createCorpusIndexing,
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
      query: retrievalQuery,
      setQuery: setRetrievalQuery,
      topK: retrievalTopK,
      setTopK: setRetrievalTopK,
      searchBusy: retrievalSearchBusy,
      searchError: retrievalSearchError,
      searchResult: retrievalSearchResult,
      search: runRetrievalSearch,
    },
    refreshCatalog,
    refreshing: profilesLoading || chunkBundlesLoading,
  };
}

export type EmbeddingIndexingPipeline = ReturnType<typeof useEmbeddingIndexingPipeline>;
