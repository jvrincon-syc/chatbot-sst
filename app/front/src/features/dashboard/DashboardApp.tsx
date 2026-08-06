import { FormEvent, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { validateOcrThresholdPercent } from "../../ocrSettings.js";
import { matchesDocumentReviewQuery } from "../../documentReview.js";
import { ChunkingWorkspace } from "../chunking/ChunkingWorkspace.js";
import { EmbeddingIndexingWorkspace } from "../embeddingIndexing/EmbeddingIndexingWorkspace.js";
import {
  DashboardNotice,
  DashboardSummary,
  LlamaStatusPanel,
  PipelinePanel,
  UploadPanel,
} from "./components/DashboardChrome.js";
import { DashboardSidebar } from "./components/DashboardSidebar.js";
import { InventoryWorkspace, ReviewWorkspace } from "./components/DocumentWorkspaces.js";
import {
  loadDashboardStatus,
  promoteDashboardStaging,
  runDashboardPipeline,
  saveDashboardSettings,
  submitDashboardReview,
  uploadDashboardDocument,
  validateDashboardBundle,
} from "./dashboardApi.js";
import { DASHBOARD_VIEWS } from "./dashboardNavigation.js";
import { useDashboardPreferences } from "./hooks/useDashboardPreferences.js";
import {
  DEFAULT_APPROVE_REASON,
  DEFAULT_REJECT_REASON,
  type ActionResult,
  type DashboardUploadForm,
  type DocumentRecord,
  type StatusPayload,
  viewTitles,
} from "./dashboardTypes.js";
import type { NoticeTone } from "./typesInternal.js";

type DashboardNoticeState = {
  tone: NoticeTone;
  message: string;
} | null;

const STATUS_REFRESH_ERROR = "No se pudo cargar el estado.";

export function DashboardApp() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<DashboardNoticeState>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [ingestionFilter, setIngestionFilter] = useState("all");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [lastResult, setLastResult] = useState<ActionResult | null>(null);
  const [uploadForm, setUploadForm] = useState<DashboardUploadForm>({
    category: "general_sst",
    folder: "manuales",
    file: null,
  });

  const {
    preferences,
    setActiveView,
    setEmbeddingIndexingActiveStage,
    setLlamaControls,
    setOcrThresholdInput,
    setSelectedDocumentId,
  } = useDashboardPreferences(status);

  const isChunkingView = preferences.activeView === "chunking";
  const isStandaloneWorkspaceView =
    preferences.activeView === "chunking" || preferences.activeView === "embedding-indexing";

  const loadStatus = async () => {
    setLoading(true);
    try {
      const payload = await loadDashboardStatus();
      setStatus(payload);
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : STATUS_REFRESH_ERROR,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  const ocrThresholdValidation = useMemo(
    () => validateOcrThresholdPercent(preferences.ocrThresholdInput),
    [preferences.ocrThresholdInput],
  );

  const documents = status?.documents ?? [];
  const pendingReview = status?.needsReview ?? [];

  const categories = useMemo(() => {
    return Array.from(
      new Set(documents.map((document) => document.category).filter(Boolean)),
    ).sort() as string[];
  }, [documents]);

  const ingestionMethodOptions = useMemo(() => {
    return Array.from(
      new Map(
        documents
          .filter((document) => document.ingestionProvider !== "unregistered")
          .map((document) => [
            document.ingestionMethod,
            {
              value: `method:${document.ingestionMethod}`,
              label: document.ingestionMethodLabel,
            },
          ]),
      ).values(),
    ).sort((left, right) => left.label.localeCompare(right.label));
  }, [documents]);

  const filteredDocuments = useMemo(() => {
    return documents.filter((document) => {
      const matchesQuery = matchesDocumentReviewQuery(document, query);
      const matchesStatus =
        statusFilter === "all" ||
        document.displayStatus === statusFilter ||
        document.processingStatus === statusFilter ||
        document.reviewStatus === statusFilter;
      const matchesIngestion =
        ingestionFilter === "all" ||
        ingestionFilter === `provider:${document.ingestionProvider}` ||
        ingestionFilter === `method:${document.ingestionMethod}`;
      return matchesQuery && matchesStatus && matchesIngestion;
    });
  }, [documents, ingestionFilter, query, statusFilter]);

  const selectedReviewDocument = resolveSelectedDocument(
    preferences.selectedDocumentIds.review,
    pendingReview,
  );
  const selectedInventoryDocument = resolveSelectedDocument(
    preferences.selectedDocumentIds.inventory,
    filteredDocuments,
  );

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!uploadForm.file) {
      setNotice({ tone: "warning", message: "Selecciona un archivo .pdf o .md." });
      return;
    }

    setBusyAction("upload");
    try {
      const payload = await uploadDashboardDocument(uploadForm);
      setLastResult(payload);
      setUploadForm((current) => ({ ...current, file: null }));
      setNotice({
        tone: "success",
        message: `Documento cargado: ${payload.sourceRelpath ?? "sin ruta"}`,
      });
      await loadStatus();
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo cargar archivo.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const submitReview = async (document: DocumentRecord, decision: "approved" | "rejected") => {
    const fallback = decision === "approved" ? DEFAULT_APPROVE_REASON : DEFAULT_REJECT_REASON;
    const reason = (reviewNotes[document.documentId] || fallback).trim();
    setBusyAction(`${decision}:${document.documentId}`);
    try {
      const payload = await submitDashboardReview({
        documentId: document.documentId,
        decision,
        reason,
      });
      setLastResult(payload);
      setNotice({
        tone: "success",
        message: `${decision === "approved" ? "Aprobado" : "Rechazado"}: ${document.documentName}`,
      });
      await loadStatus();
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo guardar decision.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const runPipeline = async () => {
    if (ocrThresholdValidation.status !== "valid") {
      setNotice({ tone: "warning", message: ocrThresholdValidation.message });
      return;
    }
    setBusyAction("pipeline");
    try {
      const payload = await runDashboardPipeline({
        controls: preferences.llamaControls,
        ocrReviewThresholdPercent: ocrThresholdValidation.value,
      });
      setLastResult(payload);
      if (payload.statusPayload) {
        setStatus(payload.statusPayload);
      }
      setNotice({
        tone: "success",
        message: `Ingesta staging finalizada: ${payload.runId ?? "sin run_id"}`,
      });
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo ejecutar ingesta.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const saveSettings = async () => {
    if (ocrThresholdValidation.status !== "valid") {
      setNotice({ tone: "warning", message: ocrThresholdValidation.message });
      return;
    }
    setBusyAction("settings");
    try {
      const payload = await saveDashboardSettings({
        ocrReviewThresholdPercent: ocrThresholdValidation.value,
        llamaControls: preferences.llamaControls,
      });
      const savedPercent =
        payload.settings?.ocrReviewThresholdPercent ?? ocrThresholdValidation.value;
      setLastResult({
        ok: payload.ok,
        summary: { ocrReviewThresholdPercent: savedPercent },
      });
      setNotice({
        tone: "success",
        message: "Ajustes guardados.",
      });
      if (payload.status) {
        setStatus(payload.status);
      } else {
        await loadStatus();
      }
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo guardar configuracion.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const runValidation = async () => {
    setBusyAction("validate");
    try {
      const payload = await validateDashboardBundle({
        stagingRoot: lastResult?.stagingRoot,
      });
      setLastResult(payload);
      setNotice({
        tone: payload.status === "passed" ? "success" : "warning",
        message: `Validacion ${payload.target === "staging" ? "staging" : "oficial"} ${payload.status}: ${
          payload.errors ?? 0
        } errores.`,
      });
      await loadStatus();
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo validar.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const promoteStaging = async () => {
    if (!lastResult?.stagingRoot) {
      setNotice({
        tone: "warning",
        message: "Primero ejecuta y valida una ingesta en staging.",
      });
      return;
    }
    setBusyAction("promote");
    try {
      const payload = await promoteDashboardStaging({
        stagingRoot: lastResult.stagingRoot,
      });
      setLastResult(payload);
      setNotice({
        tone: "success",
        message: `Staging promovido a salida oficial: ${payload.runId ?? "sin run_id"}`,
      });
      await loadStatus();
    } catch (error) {
      setNotice({
        tone: "danger",
        message: error instanceof Error ? error.message : "No se pudo promover staging.",
      });
    } finally {
      setBusyAction(null);
    }
  };

  const handleDocumentSelect = (view: "review" | "inventory", document: DocumentRecord) => {
    setSelectedDocumentId(view, document.documentId);
  };

  return (
    <div className={isChunkingView ? "app-shell chunking-mode" : "app-shell"}>
      <DashboardSidebar activeView={preferences.activeView} onViewChange={setActiveView} />
      <main className={isChunkingView ? "workspace chunking-workspace" : "workspace"}>
        <header className="topbar">
          <div>
            <h1>{viewTitles[preferences.activeView]}</h1>
            <p>
              {isChunkingView
                ? "Inspeccion de corridas parent-child y evidencia de chunks"
                : `Schema ${status?.summary.schemaVersion ?? "2.0"} · ${status?.summary.runId ?? "sin run"}`}
            </p>
          </div>
          <div className="topbar-actions">
            <div className="view-switcher" aria-label="Cambiar vista">
              {DASHBOARD_VIEWS.map((item) => (
                <button
                  className={preferences.activeView === item.view ? "active" : ""}
                  onClick={() => setActiveView(item.view)}
                  type="button"
                  key={item.view}
                  title={item.title}
                >
                  {item.switcherLabel}
                </button>
              ))}
            </div>
            <button className="ghost-button" onClick={loadStatus} disabled={loading}>
              <RefreshCw size={16} />
              Actualizar
            </button>
            <span className="user-chip">Operaciones SST</span>
          </div>
        </header>

        {notice ? <DashboardNotice tone={notice.tone} message={notice.message} /> : null}

        {!isStandaloneWorkspaceView ? <DashboardSummary summary={status?.summary ?? null} /> : null}

        {preferences.activeView === "operations" ? (
          <>
            <LlamaStatusPanel
              status={status?.llamaFirst ?? null}
              controls={preferences.llamaControls}
              ocrThresholdInput={preferences.ocrThresholdInput}
              ocrThresholdValidation={ocrThresholdValidation}
              settingsBusy={busyAction === "settings"}
              onControlsChange={setLlamaControls}
              onOcrThresholdChange={setOcrThresholdInput}
              onSaveSettings={saveSettings}
            />

            <section className="primary-grid">
              <UploadPanel
                categories={categories}
                form={uploadForm}
                busy={busyAction === "upload"}
                onChange={setUploadForm}
                onSubmit={handleUpload}
              />
              <PipelinePanel
                validation={status?.validation ?? null}
                lastResult={lastResult}
                busyAction={busyAction}
                controls={preferences.llamaControls}
                pipelineBlockedReason={
                  ocrThresholdValidation.status === "valid"
                    ? null
                    : ocrThresholdValidation.message
                }
                onRunPipeline={runPipeline}
                onValidate={runValidation}
                onPromote={promoteStaging}
              />
            </section>
          </>
        ) : null}

        {preferences.activeView === "review" ? (
          <ReviewWorkspace
            documents={pendingReview}
            busyAction={busyAction}
            notes={reviewNotes}
            selectedDocument={selectedReviewDocument}
            selectedDocumentId={selectedReviewDocument?.documentId ?? null}
            onSelect={(document) => handleDocumentSelect("review", document)}
            onNoteChange={(documentId, value) =>
              setReviewNotes((current) => ({ ...current, [documentId]: value }))
            }
            onReview={submitReview}
          />
        ) : null}

        {preferences.activeView === "inventory" ? (
          <InventoryWorkspace
            documents={filteredDocuments}
            total={documents.length}
            query={query}
            statusFilter={statusFilter}
            ingestionFilter={ingestionFilter}
            ingestionMethodOptions={ingestionMethodOptions}
            selectedDocument={selectedInventoryDocument}
            selectedDocumentId={selectedInventoryDocument?.documentId ?? null}
            onSelect={(document) => handleDocumentSelect("inventory", document)}
            onQueryChange={setQuery}
            onStatusFilterChange={setStatusFilter}
            onIngestionFilterChange={setIngestionFilter}
          />
        ) : null}

        {preferences.activeView === "chunking" ? <ChunkingWorkspace /> : null}

        {preferences.activeView === "embedding-indexing" ? (
          <EmbeddingIndexingWorkspace
            activeStage={preferences.embeddingIndexing.activeStage}
            onStageChange={setEmbeddingIndexingActiveStage}
          />
        ) : null}
      </main>
    </div>
  );
}

function resolveSelectedDocument(
  preferredDocumentId: string | null,
  documents: DocumentRecord[],
) {
  if (preferredDocumentId) {
    const selected = documents.find((document) => document.documentId === preferredDocumentId);
    if (selected) {
      return selected;
    }
  }

  return documents[0] ?? null;
}
