import { useEffect, useMemo, useState } from "react";
import {
  createChunkingRun,
  loadChunkingChildren,
  loadChunkingParents,
  loadChunkingProfiles,
  loadChunkingRun,
  loadChunkingRunDocuments,
  loadChunkingStoredDocuments,
  loadChunkingValidationOptional,
} from "./chunkingApi.js";
import {
  chunkingPaginationLabel,
  chunkingRunIsTerminalStatus,
  chunkingRunProgressPercent,
  createChunkingIdempotencyKey,
  DEFAULT_CHUNKING_PROFILE_ID,
  mergeChunkingFormState,
  parseChunkingDocumentIds,
  type ChunkingFormState,
} from "./chunkingState.js";
import type {
  ChunkingChildrenPage,
  ChunkingParentsPage,
  ChunkingProfile,
  ChunkingRunDocumentsPage,
  ChunkingRunSummary,
  ChunkingStoredDocumentsPage,
  ChunkingValidation,
} from "./chunkingTypes.js";

export type ChunkingNoticeState =
  | {
      tone: "info" | "success" | "warning" | "danger";
      message: string;
    }
  | null;

// Todo el estado de servidor y la orquestacion de la pantalla de chunking.
// Los paneles solo reciben datos ya resueltos y callbacks.
export function useChunkingWorkspace() {
  const [profiles, setProfiles] = useState<ChunkingProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [notice, setNotice] = useState<ChunkingNoticeState>(null);

  const [form, setForm] = useState<ChunkingFormState>(() => ({
    scope: "corpus",
    documentIdsInput: "",
    profileId: DEFAULT_CHUNKING_PROFILE_ID,
    force: false,
    idempotencyKey: createChunkingIdempotencyKey(),
  }));

  const [launchBusy, setLaunchBusy] = useState(false);
  const [runSummary, setRunSummary] = useState<ChunkingRunSummary | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [documentsPage, setDocumentsPage] = useState<ChunkingRunDocumentsPage | null>(null);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentsPageNumber, setDocumentsPageNumber] = useState(1);
  const [storedDocumentsPage, setStoredDocumentsPage] = useState<ChunkingStoredDocumentsPage | null>(null);
  const [storedDocumentsLoading, setStoredDocumentsLoading] = useState(false);
  const [storedDocumentsError, setStoredDocumentsError] = useState<string | null>(null);
  const [storedDocumentsPageNumber, setStoredDocumentsPageNumber] = useState(1);

  const [validation, setValidation] = useState<ChunkingValidation | null>(null);
  const [validationLoading, setValidationLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  const [parentsPage, setParentsPage] = useState<ChunkingParentsPage | null>(null);
  const [parentsLoading, setParentsLoading] = useState(false);
  const [parentsError, setParentsError] = useState<string | null>(null);
  const [parentsPageNumber, setParentsPageNumber] = useState(1);
  const [selectedParentId, setSelectedParentId] = useState<string | null>(null);

  const [childrenPage, setChildrenPage] = useState<ChunkingChildrenPage | null>(null);
  const [childrenLoading, setChildrenLoading] = useState(false);
  const [childrenError, setChildrenError] = useState<string | null>(null);
  const [childrenPageNumber, setChildrenPageNumber] = useState(1);

  const updateForm = (next: Partial<ChunkingFormState>) => {
    setForm((current) => mergeChunkingFormState(current, next));
  };

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.profileId === form.profileId) ?? profiles[0] ?? null,
    [form.profileId, profiles],
  );

  const parsedDocumentIds = useMemo(
    () => parseChunkingDocumentIds(form.documentIdsInput),
    [form.documentIdsInput],
  );

  const runProgress = useMemo(
    () =>
      runSummary
        ? chunkingRunProgressPercent({
            requestedDocuments: runSummary.requestedDocuments,
            completedDocuments: runSummary.completedDocuments,
          })
        : 0,
    [runSummary],
  );

  const validationValue =
    validation?.status ??
    (runSummary && !chunkingRunIsTerminalStatus(runSummary.status) ? "pendiente" : "sin reporte");

  const isRunMode = runSummary !== null;

  useEffect(() => {
    let cancelled = false;
    async function loadProfiles() {
      setProfilesLoading(true);
      setProfilesError(null);
      try {
        const payload = await loadChunkingProfiles();
        if (cancelled) return;
        setProfiles(payload);
        if (payload.length > 0) {
          setForm((current) => {
            if (current.profileId && payload.some((profile) => profile.profileId === current.profileId)) {
              return current;
            }
            return mergeChunkingFormState(current, { profileId: payload[0].profileId });
          });
        }
      } catch (error) {
        if (cancelled) return;
        setProfilesError(error instanceof Error ? error.message : "No se pudieron cargar perfiles.");
      } finally {
        if (!cancelled) setProfilesLoading(false);
      }
    }

    void loadProfiles();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    void loadStoredSnapshot(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const activeDocumentIds = isRunMode
      ? (documentsPage?.items ?? []).map((item) => item.documentId)
      : (storedDocumentsPage?.items ?? []).map((item) => item.documentId);
    if (!selectedDocumentId) {
      return;
    }
    if (!activeDocumentIds.includes(selectedDocumentId)) {
      setSelectedDocumentId(null);
      setParentsPage(null);
      setSelectedParentId(null);
      setChildrenPage(null);
    }
  }, [documentsPage, isRunMode, selectedDocumentId, storedDocumentsPage]);

  useEffect(() => {
    if (!parentsPage) {
      return;
    }
    if (
      selectedParentId &&
      parentsPage.items.some((item) => item.chunkId === selectedParentId)
    ) {
      return;
    }
    const firstParent = parentsPage.items[0];
    if (firstParent) {
      setSelectedParentId(firstParent.chunkId);
      void loadChildrenForParent(firstParent.chunkId);
    } else {
      setSelectedParentId(null);
      setChildrenPage(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parentsPage]);

  const loadRunSnapshot = async (runId: string, page = documentsPageNumber) => {
    setRunLoading(true);
    setDocumentsLoading(true);
    setValidationLoading(true);
    setRunError(null);
    setDocumentsError(null);
    setValidationError(null);
    try {
      const [run, docs] = await Promise.all([
        loadChunkingRun(runId),
        loadChunkingRunDocuments({ runId, page }),
      ]);
      setRunSummary(run);
      setDocumentsPage(docs);
      setDocumentsPageNumber(docs.page);
      if (docs.items.length > 0) {
        const nextDocumentId =
          docs.items.find((item) => item.documentId === selectedDocumentId)?.documentId ??
          docs.items[0].documentId;
        setSelectedDocumentId(nextDocumentId);
        await loadParentsForDocument(nextDocumentId, 1, run.runId);
      } else {
        setSelectedDocumentId(null);
        setParentsPage(null);
        setSelectedParentId(null);
        setChildrenPage(null);
      }
      try {
        const validationReport = await loadChunkingValidationOptional(runId);
        setValidation(validationReport);
        if (validationReport) {
          setValidationError(null);
        } else if (chunkingRunIsTerminalStatus(run.status)) {
          setValidationError("No se encontro un reporte de validacion para esta corrida.");
        } else {
          setValidationError(null);
        }
      } catch (validationLoadError) {
        const message =
          validationLoadError instanceof Error
            ? validationLoadError.message
            : "No se pudo cargar la validacion.";
        setValidationError(message);
      }
      setNotice({
        tone: "success",
        message: `Corrida ${run.status}: ${run.runId.slice(0, 12)}...`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudo cargar la corrida.";
      setRunError(message);
      setDocumentsError(message);
      setValidationError(message);
      setNotice({ tone: "danger", message });
    } finally {
      setRunLoading(false);
      setDocumentsLoading(false);
      setValidationLoading(false);
    }
  };

  const loadStoredSnapshot = async (page = storedDocumentsPageNumber) => {
    setStoredDocumentsLoading(true);
    setStoredDocumentsError(null);
    try {
      const docs = await loadChunkingStoredDocuments({ page });
      setStoredDocumentsPage(docs);
      setStoredDocumentsPageNumber(docs.page);
      if (docs.items.length > 0) {
        const nextDocumentId =
          docs.items.find((item) => item.documentId === selectedDocumentId)?.documentId ??
          docs.items[0].documentId;
        setSelectedDocumentId(nextDocumentId);
        await loadParentsForDocument(nextDocumentId, 1, undefined);
      } else {
        setSelectedDocumentId(null);
        setParentsPage(null);
        setSelectedParentId(null);
        setChildrenPage(null);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "No se pudieron cargar los documentos ya chunkeados.";
      setStoredDocumentsError(message);
      setNotice({ tone: "warning", message });
    } finally {
      setStoredDocumentsLoading(false);
    }
  };

  const loadParentsForDocument = async (documentId: string, page = 1, currentRunId = runSummary?.runId) => {
    setParentsLoading(true);
    setParentsError(null);
    try {
      const payload = await loadChunkingParents({
        documentId,
        runId: currentRunId ?? undefined,
        page,
      });
      setParentsPage(payload);
      setParentsPageNumber(payload.page);
      if (payload.items.length > 0) {
        const nextParentId =
          payload.items.find((item) => item.chunkId === selectedParentId)?.chunkId ??
          payload.items[0].chunkId;
        setSelectedParentId(nextParentId);
        await loadChildrenForParent(nextParentId, 1);
      } else {
        setSelectedParentId(null);
        setChildrenPage(null);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudieron cargar los parents.";
      setParentsError(message);
      setNotice({ tone: "warning", message });
    } finally {
      setParentsLoading(false);
    }
  };

  const loadChildrenForParent = async (parentId: string, page = 1) => {
    setChildrenLoading(true);
    setChildrenError(null);
    try {
      const payload = await loadChunkingChildren({
        parentId,
        page,
      });
      setChildrenPage(payload);
      setChildrenPageNumber(payload.page);
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudieron cargar los children.";
      setChildrenError(message);
      setNotice({ tone: "warning", message });
    } finally {
      setChildrenLoading(false);
    }
  };

  const handleLaunchRun = async () => {
    setLaunchBusy(true);
    setRunError(null);
    setNotice(null);
    try {
      const documentIds =
        form.scope === "documents"
          ? parsedDocumentIds
          : [];
      if (form.scope === "documents" && documentIds.length === 0) {
        setNotice({
          tone: "warning",
          message: "Agrega al menos un document_id cuando la corrida sea por documentos.",
        });
        return;
      }
      if (!form.profileId.trim()) {
        setNotice({ tone: "warning", message: "Selecciona un perfil de chunking." });
        return;
      }
      const run = await createChunkingRun({
        idempotencyKey: form.idempotencyKey,
        request: {
          scope: form.scope,
          documentIds,
          profileId: form.profileId,
          force: form.force,
        },
      });
      setRunSummary(run);
      setNotice({
        tone: "success",
        message: `Corrida creada: ${run.runId.slice(0, 12)}...`,
      });
      await loadRunSnapshot(run.runId, 1);
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudo crear la corrida.";
      setNotice({ tone: "danger", message });
      setRunError(message);
    } finally {
      setLaunchBusy(false);
    }
  };

  const handleRefresh = async () => {
    if (!runSummary?.runId) {
      await loadStoredSnapshot(storedDocumentsPageNumber);
      return;
    }
    await loadRunSnapshot(runSummary.runId, documentsPageNumber);
  };

  const handleDocumentPageChange = async (page: number) => {
    if (!runSummary?.runId) {
      setStoredDocumentsPageNumber(page);
      await loadStoredSnapshot(page);
      return;
    }
    setDocumentsPageNumber(page);
    setDocumentsLoading(true);
    try {
      const payload = await loadChunkingRunDocuments({ runId: runSummary.runId, page });
      setDocumentsPage(payload);
      if (payload.items.length > 0) {
        const nextDocumentId =
          payload.items.find((item) => item.documentId === selectedDocumentId)?.documentId ??
          payload.items[0].documentId;
        setSelectedDocumentId(nextDocumentId);
        await loadParentsForDocument(nextDocumentId, 1, runSummary.runId);
      } else {
        setSelectedDocumentId(null);
        setParentsPage(null);
        setSelectedParentId(null);
        setChildrenPage(null);
      }
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "No se pudieron cargar los documentos.");
    } finally {
      setDocumentsLoading(false);
    }
  };

  const handleSelectDocument = async (documentId: string) => {
    setSelectedDocumentId(documentId);
    await loadParentsForDocument(documentId, 1, runSummary?.runId);
  };

  const handleParentsPageChange = async (page: number) => {
    if (!selectedDocumentId) {
      return;
    }
    await loadParentsForDocument(selectedDocumentId, page);
  };

  const handleChildrenPageChange = async (page: number) => {
    if (!selectedParentId) {
      return;
    }
    await loadChildrenForParent(selectedParentId, page);
  };

  const selectedParent = parentsPage?.items.find((item) => item.chunkId === selectedParentId) ?? null;
  const documentPanelPage = isRunMode ? documentsPage : storedDocumentsPage;
  const documentPanelLoading = isRunMode ? documentsLoading : storedDocumentsLoading;
  const documentPanelError = isRunMode ? documentsError : storedDocumentsError;
  const documentPanelTitle = isRunMode ? "Documentos de la corrida" : "Chunks persistidos";
  const documentPanelSubtitle = documentPanelPage
    ? chunkingPaginationLabel(documentPanelPage.page, documentPanelPage.totalPages, documentPanelPage.totalItems)
    : isRunMode
      ? "Sin documentos cargados"
      : "Sin documentos chunkeados";
  const documentRows = isRunMode
    ? (documentsPage?.items ?? []).map((document) => ({
        documentId: document.documentId,
        normalizedRelpath: document.normalizedRelpath,
        primaryValue: document.status,
        secondaryValue: document.reused ? "Si" : "No",
      }))
    : (storedDocumentsPage?.items ?? []).map((document) => ({
        documentId: document.documentId,
        normalizedRelpath: document.normalizedRelpath,
        primaryValue: document.profileId,
        secondaryValue: `${document.parentCount} / ${document.childCount}`,
      }));
  const documentPrimaryHeader = isRunMode ? "Estado" : "Perfil";
  const documentSecondaryHeader = isRunMode ? "Reutilizado" : "Parents / Children";

  const handleSelectParent = (parentId: string) => {
    setSelectedParentId(parentId);
    void loadChildrenForParent(parentId, 1);
  };

  const regenerateIdempotencyKey = () =>
    updateForm({ idempotencyKey: createChunkingIdempotencyKey() });

  return {
    notice,
    form,
    updateForm,
    profiles,
    profilesLoading,
    profilesError,
    selectedProfile,
    parsedDocumentIds,
    launchBusy,
    regenerateIdempotencyKey,
    handleLaunchRun,
    runSummary,
    runLoading,
    runError,
    runProgress,
    handleRefresh,
    validation,
    validationLoading,
    validationError,
    validationValue,
    isRunMode,
    documentPanelTitle,
    documentPanelSubtitle,
    documentPanelPage,
    documentPanelLoading,
    documentPanelError,
    documentRows,
    documentPrimaryHeader,
    documentSecondaryHeader,
    selectedDocumentId,
    handleSelectDocument,
    handleDocumentPageChange,
    parentsPage,
    parentsLoading,
    parentsError,
    selectedParentId,
    selectedParent,
    handleSelectParent,
    handleParentsPageChange,
    childrenPage,
    childrenLoading,
    childrenError,
    handleChildrenPageChange,
  };
}
