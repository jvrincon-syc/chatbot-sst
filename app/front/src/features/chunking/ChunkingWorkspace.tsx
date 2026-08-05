import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Blocks,
  CheckCircle2,
  Copy,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Settings2,
  SplitSquareHorizontal,
  TriangleAlert,
} from "lucide-react";
import { DashboardNotice } from "../dashboard/components/DashboardChrome.js";
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
  mergeChunkingFormState,
  chunkingProfileSummary,
  chunkingRunProgressPercent,
  chunkingRunIsTerminalStatus,
  chunkingRunStatusLabel,
  chunkingRunStatusTone,
  createChunkingIdempotencyKey,
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

type ChunkingNoticeState =
  | {
      tone: "info" | "success" | "warning" | "danger";
      message: string;
    }
  | null;

const DEFAULT_PROFILE_ID = "local-structural-v1";

export function ChunkingWorkspace() {
  const [profiles, setProfiles] = useState<ChunkingProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [notice, setNotice] = useState<ChunkingNoticeState>(null);

  const [form, setForm] = useState<ChunkingFormState>(() => ({
    scope: "corpus",
    documentIdsInput: "",
    profileId: DEFAULT_PROFILE_ID,
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

  return (
    <section className="chunking-workspace">
      {notice ? <DashboardNotice tone={notice.tone} message={notice.message} /> : null}

      <section className="chunking-hero">
        <ChunkingLaunchPanel
          form={form}
          profiles={profiles}
          profilesError={profilesError}
          profilesLoading={profilesLoading}
          parsedDocumentIds={parsedDocumentIds}
          selectedProfile={selectedProfile}
          busy={launchBusy}
          onChange={updateForm}
          onLaunch={handleLaunchRun}
          onRegenerateKey={() => updateForm({ idempotencyKey: createChunkingIdempotencyKey() })}
        />
        <ChunkingProfilePanel
          profile={selectedProfile}
          profilesLoading={profilesLoading}
          status={runSummary}
          runLoading={runLoading}
          onRefresh={handleRefresh}
        />
      </section>

      <section className="chunking-summary-grid">
        <ChunkingMetricCard label="Corrida activa" value={runSummary?.runId ?? "sin corrida"} tone="neutral" icon={<Blocks size={18} />} />
        <ChunkingMetricCard label="Estado" value={runSummary ? chunkingRunStatusLabel(runSummary.status) : "sin estado"} tone={chunkingRunStatusTone(runSummary?.status ?? "queued")} icon={<CheckCircle2 size={18} />} />
        <ChunkingMetricCard label="Progreso" value={`${runProgress}%`} tone={runProgress === 100 ? "success" : "warning"} icon={<Settings2 size={18} />} />
        <ChunkingMetricCard label="Validation" value={validationValue} tone={validation?.status === "passed" ? "success" : validationValue === "pendiente" ? "neutral" : "warning"} icon={<TriangleAlert size={18} />} />
      </section>

      <section className="chunking-grid">
        <ChunkingRunPanel
          run={runSummary}
          loading={runLoading}
          error={runError}
          validation={validation}
          validationLoading={validationLoading}
          validationError={validationError}
          onRefresh={handleRefresh}
        />
        <ChunkingDocumentsPanel
          title={documentPanelTitle}
          subtitle={documentPanelSubtitle}
          rows={documentRows}
          page={documentPanelPage?.page ?? 1}
          totalPages={documentPanelPage?.totalPages ?? 0}
          loading={documentPanelLoading}
          error={documentPanelError}
          selectedDocumentId={selectedDocumentId}
          primaryHeader={documentPrimaryHeader}
          secondaryHeader={documentSecondaryHeader}
          emptyMessage={
            isRunMode
              ? "No hay documentos para mostrar."
              : "No se encontraron documentos con chunks persistidos."
          }
          onSelectDocument={handleSelectDocument}
          onPageChange={handleDocumentPageChange}
        />
      </section>

      <section className="chunking-inspector-grid">
        <ChunkingParentsPanel
          documentId={selectedDocumentId}
          parentsPage={parentsPage}
          loading={parentsLoading}
          error={parentsError}
          selectedParentId={selectedParentId}
          onSelectParent={(parentId) => {
            setSelectedParentId(parentId);
            void loadChildrenForParent(parentId, 1);
          }}
          onPageChange={handleParentsPageChange}
        />
        <ChunkingChildrenPanel
          parent={selectedParent}
          childrenPage={childrenPage}
          loading={childrenLoading}
          error={childrenError}
          onPageChange={handleChildrenPageChange}
        />
      </section>
    </section>
  );
}

function ChunkingLaunchPanel({
  form,
  profiles,
  profilesError,
  profilesLoading,
  parsedDocumentIds,
  selectedProfile,
  busy,
  onChange,
  onLaunch,
  onRegenerateKey,
}: {
  form: ChunkingFormState;
  profiles: ChunkingProfile[];
  profilesError: string | null;
  profilesLoading: boolean;
  parsedDocumentIds: string[];
  selectedProfile: ChunkingProfile | null;
  busy: boolean;
  onChange: (value: Partial<ChunkingFormState>) => void;
  onLaunch: () => void;
  onRegenerateKey: () => void;
}) {
  const idCount = parsedDocumentIds.length;
  return (
    <section className="panel chunking-panel chunking-launch-panel">
      <div className="panel-heading">
        <div>
          <h2>Lanzar corrida</h2>
          <span>Contratos locales, sin rutas arbitrarias ni embeddings.</span>
        </div>
        <span className="chunking-pill">Idempotencia obligatoria</span>
      </div>
      <div className="chunking-launch-body">
        <div className="chunking-toggle-row" role="tablist" aria-label="Scope de chunking">
          <button
            type="button"
            className={form.scope === "documents" ? "chunking-toggle active" : "chunking-toggle"}
            onClick={() => onChange({ scope: "documents" })}
          >
            Documentos
          </button>
          <button
            type="button"
            className={form.scope === "corpus" ? "chunking-toggle active" : "chunking-toggle"}
            onClick={() => onChange({ scope: "corpus" })}
          >
            Corpus
          </button>
        </div>
        <label className="chunking-field">
          Perfil
          <select
            value={form.profileId}
            disabled={profilesLoading || profiles.length === 0}
            onChange={(event) => onChange({ profileId: event.target.value })}
          >
            {profiles.length === 0 ? <option value={DEFAULT_PROFILE_ID}>{DEFAULT_PROFILE_ID}</option> : null}
            {profiles.map((profile) => (
              <option value={profile.profileId} key={profile.profileId}>
                {profile.profileId}
              </option>
            ))}
          </select>
          {profilesError ? <span className="chunking-field-note error">{profilesError}</span> : null}
        </label>
        <label className="chunking-field">
          Document IDs
          <textarea
            value={form.documentIdsInput}
            disabled={form.scope === "corpus"}
            placeholder="doc_001\ndoc_002"
            onChange={(event) => onChange({ documentIdsInput: event.target.value })}
          />
          <span className="chunking-field-note">
            {form.scope === "corpus"
              ? "La corrida usara todos los documentos del inventario."
              : `${idCount} IDs detectados. Se aceptan lineas o comas.`}
          </span>
        </label>
        <div className="chunking-inline-grid">
          <label className="chunking-checkbox">
            <input
              type="checkbox"
              checked={form.force}
              onChange={(event) => onChange({ force: event.target.checked })}
            />
            Forzar reprocesado
          </label>
          <div className="chunking-key-row">
            <label className="chunking-field">
              Idempotency-Key
              <input
                value={form.idempotencyKey}
                onChange={(event) => onChange({ idempotencyKey: event.target.value })}
              />
            </label>
            <button className="secondary-button" type="button" onClick={onRegenerateKey}>
              <Copy size={16} />
              Regenerar
            </button>
          </div>
        </div>
        <div className="chunking-launch-actions">
          <button className="primary-button" type="button" onClick={onLaunch} disabled={busy}>
            {busy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Iniciar chunking
          </button>
          <span className="chunking-launch-hint">
            {selectedProfile ? chunkingProfileSummary(selectedProfile) : "Sin perfil cargado."}
          </span>
        </div>
      </div>
    </section>
  );
}

function ChunkingProfilePanel({
  profile,
  profilesLoading,
  status,
  runLoading,
  onRefresh,
}: {
  profile: ChunkingProfile | null;
  profilesLoading: boolean;
  status: ChunkingRunSummary | null;
  runLoading: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="panel chunking-panel chunking-profile-panel">
      <div className="panel-heading">
        <div>
          <h2>Perfil activo</h2>
          <span>Resumen de la configuracion local y del ultimo estado cargado.</span>
        </div>
        <button className="ghost-button" type="button" onClick={onRefresh} disabled={runLoading}>
          <RefreshCw size={16} />
          Actualizar
        </button>
      </div>
      {profilesLoading ? (
        <div className="chunking-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando perfiles locales...</span>
        </div>
      ) : profile ? (
        <div className="chunking-profile-body">
          <dl className="chunking-profile-grid">
            <div>
              <dt>Perfil</dt>
              <dd>{profile.profileId}</dd>
            </div>
            <div>
              <dt>Children min</dt>
              <dd>{profile.childMinTokens}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>{profile.childTargetTokens}</dd>
            </div>
            <div>
              <dt>Max</dt>
              <dd>{profile.childMaxTokens}</dd>
            </div>
            <div>
              <dt>Overlap</dt>
              <dd>{Math.round(profile.overlapRatio * 100)}%</dd>
            </div>
            <div>
              <dt>Overlap min/max</dt>
              <dd>
                {profile.overlapMinTokens} / {profile.overlapMaxTokens}
              </dd>
            </div>
          </dl>
          <div className="chunking-profile-note">
            <Blocks size={16} />
            <span>{chunkingProfileSummary(profile)}</span>
          </div>
          <div className="chunking-profile-state">
            <span>Ultima corrida</span>
            <strong>{status ? `${status.status} · ${status.runId.slice(0, 12)}...` : "Sin corrida"}</strong>
          </div>
        </div>
      ) : (
        <div className="chunking-empty">
          <AlertCircle size={20} />
          <span>No hay perfiles disponibles para chunking.</span>
        </div>
      )}
    </section>
  );
}

function ChunkingRunPanel({
  run,
  loading,
  error,
  validation,
  validationLoading,
  validationError,
  onRefresh,
}: {
  run: ChunkingRunSummary | null;
  loading: boolean;
  error: string | null;
  validation: ChunkingValidation | null;
  validationLoading: boolean;
  validationError: string | null;
  onRefresh: () => void;
}) {
  return (
    <section className="panel chunking-panel">
      <div className="panel-heading">
        <div>
          <h2>Estado de corrida</h2>
          <span>Progreso, warnings y verificacion de la ejecucion actual.</span>
        </div>
        <button className="ghost-button" type="button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} />
          Refrescar
        </button>
      </div>
      <div className="chunking-panel-body">
        {loading ? (
          <div className="chunking-empty">
            <Loader2 className="spin" size={20} />
            <span>Cargando estado de corrida...</span>
          </div>
        ) : error ? (
          <div className="chunking-empty">
            <TriangleAlert size={20} />
            <span>{error}</span>
          </div>
        ) : run ? (
          <>
            <div className="chunking-status-row">
              <span className={`chunking-status-chip ${chunkingRunStatusTone(run.status)}`}>
                {chunkingRunStatusLabel(run.status)}
              </span>
              <span className="chunking-meta">Perfil {run.profileId}</span>
              <span className="chunking-meta">{run.requestedDocuments} documentos</span>
            </div>
            <div className="chunking-progress">
              <div className="chunking-progress-track">
                <div className="chunking-progress-fill" style={{ width: `${chunkingRunProgressPercent(run)}%` }} />
              </div>
              <span>{chunkingRunProgressPercent(run)}%</span>
            </div>
            <dl className="chunking-mini-metrics">
              <div>
                <dt>Solicitados</dt>
                <dd>{run.requestedDocuments}</dd>
              </div>
              <div>
                <dt>Completados</dt>
                <dd>{run.completedDocuments}</dd>
              </div>
              <div>
                <dt>Warnings</dt>
                <dd>{run.warnings.length}</dd>
              </div>
            </dl>
            <div className="chunking-links">
              <a href={run.links.self} target="_blank" rel="noreferrer">
                Ver corrida
              </a>
              <a href={run.links.documents} target="_blank" rel="noreferrer">
                Ver documentos
              </a>
              <a href={run.links.validation} target="_blank" rel="noreferrer">
                Ver validacion
              </a>
            </div>
            {run.warnings.length > 0 ? (
              <div className="chunking-warning-box">
                <TriangleAlert size={16} />
                <ul>
                  {run.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <div className="chunking-empty">
            <Search size={20} />
            <span>Sin corrida activa. Puedes inspeccionar abajo los chunks ya persistidos.</span>
          </div>
        )}
      </div>
      <div className="chunking-validation">
        <div className="panel-heading chunking-subheading">
          <div>
            <h3>Validacion</h3>
            <span>Resumen calculado por el backend para la corrida actual.</span>
          </div>
          {validationLoading ? <Loader2 className="spin" size={16} /> : null}
        </div>
        {validationError ? (
          <div className="chunking-empty compact">
            <TriangleAlert size={18} />
            <span>{validationError}</span>
          </div>
        ) : validation ? (
          <dl className="chunking-mini-metrics compact">
            <div>
              <dt>Estado</dt>
              <dd>{validation.status}</dd>
            </div>
            <div>
              <dt>Revisados</dt>
              <dd>{validation.documentsChecked}</dd>
            </div>
            <div>
              <dt>Errores</dt>
              <dd>{validation.errors}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd>{validation.warnings}</dd>
            </div>
          </dl>
        ) : (
          <div className="chunking-empty compact">
            <span>
              {run && !chunkingRunIsTerminalStatus(run.status)
                ? "La validacion se publicara cuando la corrida termine."
                : "Sin validacion disponible."}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

function ChunkingDocumentsPanel({
  title,
  subtitle,
  rows,
  page,
  totalPages,
  loading,
  error,
  selectedDocumentId,
  primaryHeader,
  secondaryHeader,
  emptyMessage,
  onSelectDocument,
  onPageChange,
}: {
  title: string;
  subtitle: string;
  rows: Array<{
    documentId: string;
    normalizedRelpath: string;
    primaryValue: string;
    secondaryValue: string;
  }>;
  page: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
  selectedDocumentId: string | null;
  primaryHeader: string;
  secondaryHeader: string;
  emptyMessage: string;
  onSelectDocument: (documentId: string) => void;
  onPageChange: (page: number) => void;
}) {
  return (
    <section className="panel chunking-panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <span>{subtitle}</span>
        </div>
      </div>
      {loading ? (
        <div className="chunking-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando documentos...</span>
        </div>
      ) : error ? (
        <div className="chunking-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : rows.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="chunking-table">
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>{primaryHeader}</th>
                  <th>{secondaryHeader}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((document) => (
                  <tr
                    key={document.documentId}
                    className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                  >
                    <td>
                      <div className="chunking-row-cell">
                        <strong>{document.documentId}</strong>
                        <span>{document.normalizedRelpath}</span>
                        <button type="button" className="row-detail-button" onClick={() => onSelectDocument(document.documentId)}>
                          Inspeccionar
                        </button>
                      </div>
                    </td>
                    <td>{document.primaryValue}</td>
                    <td>{document.secondaryValue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="chunking-empty">
          <SplitSquareHorizontal size={20} />
          <span>{emptyMessage}</span>
        </div>
      )}
    </section>
  );
}

function ChunkingParentsPanel({
  documentId,
  parentsPage,
  loading,
  error,
  selectedParentId,
  onSelectParent,
  onPageChange,
}: {
  documentId: string | null;
  parentsPage: ChunkingParentsPage | null;
  loading: boolean;
  error: string | null;
  selectedParentId: string | null;
  onSelectParent: (parentId: string) => void;
  onPageChange: (page: number) => void;
}) {
  const page = parentsPage?.page ?? 1;
  const totalPages = parentsPage?.totalPages ?? 0;
  return (
    <section className="panel chunking-panel">
      <div className="panel-heading">
        <div>
          <h2>Parents</h2>
          <span>{documentId ?? "Selecciona un documento para inspeccionar."}</span>
        </div>
      </div>
      {loading ? (
        <div className="chunking-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando parents...</span>
        </div>
      ) : error ? (
        <div className="chunking-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : parentsPage && parentsPage.items.length > 0 ? (
        <>
          <div className="chunking-list">
            {parentsPage.items.map((parent) => (
              <button
                key={parent.chunkId}
                type="button"
                className={selectedParentId === parent.chunkId ? "chunking-list-item active" : "chunking-list-item"}
                onClick={() => onSelectParent(parent.chunkId)}
              >
                <strong>
                  #{parent.ordinal} · {parent.chunkId}
                </strong>
                <span>{parent.text.slice(0, 160) || "(sin texto)"}</span>
                <small>
                  Paginas {parent.sourceSpan.pageStart ?? "?"}-{parent.sourceSpan.pageEnd ?? "?"}
                </small>
              </button>
            ))}
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="chunking-empty">
          <Search size={20} />
          <span>Sin parents disponibles para el documento seleccionado.</span>
        </div>
      )}
    </section>
  );
}

function ChunkingChildrenPanel({
  parent,
  childrenPage,
  loading,
  error,
  onPageChange,
}: {
  parent: ChunkingParentsPage["items"][number] | null;
  childrenPage: ChunkingChildrenPage | null;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
}) {
  const page = childrenPage?.page ?? 1;
  const totalPages = childrenPage?.totalPages ?? 0;
  return (
    <section className="panel chunking-panel">
      <div className="panel-heading">
        <div>
          <h2>Children</h2>
          <span>{parent ? parent.chunkId : "Selecciona un parent para continuar."}</span>
        </div>
      </div>
      {loading ? (
        <div className="chunking-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando children...</span>
        </div>
      ) : error ? (
        <div className="chunking-empty">
          <TriangleAlert size={20} />
          <span>{error}</span>
        </div>
      ) : childrenPage && childrenPage.items.length > 0 ? (
        <>
          <div className="chunking-list compact">
            {childrenPage.items.map((child) => (
              <article key={child.chunkId} className="chunking-child-card">
                <div className="chunking-child-header">
                  <strong>
                    #{child.ordinal} · {child.chunkId}
                  </strong>
                  <span>{child.tokenCount} tokens</span>
                </div>
                <p>{child.text.slice(0, 240) || "(sin texto)"}</p>
                <div className="chunking-child-meta">
                  <span>
                    Overlap prev {child.overlapPreviousTokens} / next {child.overlapNextTokens}
                  </span>
                  <span>
                    Paginas {child.sourceSpan.pageStart ?? "?"}-{child.sourceSpan.pageEnd ?? "?"}
                  </span>
                </div>
                {child.zeroOverlapReasons.length > 0 ? (
                  <div className="chunking-child-warning">
                    <TriangleAlert size={14} />
                    <span>{child.zeroOverlapReasons.join(", ")}</span>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
          <PaginationBar page={page} totalPages={totalPages} onPageChange={onPageChange} />
        </>
      ) : (
        <div className="chunking-empty">
          <ArrowRight size={20} />
          <span>Sin children disponibles para el parent seleccionado.</span>
        </div>
      )}
    </section>
  );
}

function ChunkingMetricCard({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: string;
  tone: "neutral" | "success" | "warning" | "danger";
  icon: JSX.Element;
}) {
  return (
    <article className={`metric-card chunking-metric ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function PaginationBar({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const canGoBack = page > 1;
  const canGoForward = totalPages > 0 && page < totalPages;
  return (
    <div className="chunking-pagination">
      <button type="button" className="secondary-button" disabled={!canGoBack} onClick={() => onPageChange(page - 1)}>
        Anterior
      </button>
      <span>
        Pagina {page} de {totalPages || 0}
      </span>
      <button type="button" className="secondary-button" disabled={!canGoForward} onClick={() => onPageChange(page + 1)}>
        Siguiente
      </button>
    </div>
  );
}
