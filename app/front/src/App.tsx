import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock3,
  Cloud,
  Database,
  FileText,
  FolderOpen,
  HardDrive,
  ListFilter,
  Loader2,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_LLAMA_ROUTE,
  LLAMA_ROUTE_OPTIONS,
  llamaCloudConfigFromRoute,
  matchingRoutesForServices,
  routeForServiceSelection,
  routeFromStatus,
} from "./llamaRoutes";
import { matchesDocumentReviewQuery } from "./documentReview";
import { validateOcrThresholdPercent } from "./ocrSettings";
import { pipelineRequestForControls } from "./pipelineRequest";
import type { LlamaRoute, LlamaStop } from "./llamaRoutes";
import type { OcrThresholdValidation } from "./ocrSettings";
import type { ProviderMode } from "./pipelineRequest";

type DecisionKind = "approved" | "rejected";
type ReviewStatus = "not_required" | "pending" | DecisionKind;
type ProcessingStatus = "pending" | "processed" | "failed" | "needs_review";
type DisplayStatus = ProcessingStatus | DecisionKind;
type AppView = "operations" | "review" | "inventory";

type LlamaControls = {
  providerMode: ProviderMode;
  route: LlamaRoute;
};

type ReviewDecision = {
  document_id: string;
  source_relpath: string;
  decision: DecisionKind;
  reason: string;
  decided_at: string;
};

type DocumentRecord = {
  documentId: string;
  sourceRelpath: string;
  documentName: string;
  detectedExtension: string | null;
  mimeType: string | null;
  category: string | null;
  fileSize: number;
  ingestionProvider: "local" | "llama_cloud" | "unregistered";
  ingestionProviderLabel: string;
  ingestionMethod: string;
  ingestionMethodLabel: string;
  ocrConfidenceKind: string;
  ocrConfidenceValue: number | null;
  ocrConfidencePercent: number | null;
  ocrConfidenceLabel: string;
  processingStatus: ProcessingStatus;
  displayStatus: DisplayStatus;
  reviewStatus: ReviewStatus;
  ingestionDate: string | null;
  reviewReasons: string[];
  reviewDetails: string[];
  decision: ReviewDecision | null;
};

type StatusPayload = {
  summary: {
    total: number;
    processed: number;
    needsReview: number;
    normalizedNeedsReview: number;
    failed: number;
    approved: number;
    rejected: number;
    runId: string | null;
    generatedAt: string | null;
    schemaVersion: string | null;
  };
  llamaFirst: {
    provider: string;
    configurationStatus: string;
    cloudEnabled?: boolean;
    localFallbackEnabled?: boolean;
    parseTier?: string;
    parseVersion?: string;
    classifyMode?: string;
    classifyMaxPages?: number;
    extractTier?: string;
    extractParseTier?: string;
    extractMaxPages?: number;
    classifyEnabled?: boolean;
    extractEnabled?: boolean;
    callOrder?: string[];
    error?: string;
  };
  settings: {
    ocrReviewThreshold: number;
    ocrReviewThresholdPercent: number;
  };
  documents: DocumentRecord[];
  needsReview: DocumentRecord[];
  errors: unknown[];
  validation: {
    status?: string;
    errors?: number;
    run_id?: string;
    path?: string;
  } | null;
  manifests: Record<string, string>;
};

type ActionResult = {
  ok?: boolean;
  status?: string;
  runId?: string;
  path?: string;
  stagingRoot?: string;
  sourceStagingRoot?: string;
  validationPath?: string;
  summary?: Record<string, number>;
  errors?: number;
  sourceRelpath?: string;
  target?: string;
  error?: string;
  statusPayload?: StatusPayload;
};

const DEFAULT_APPROVE_REASON =
  "Revision humana completada; apto para consumo downstream.";
const DEFAULT_REJECT_REASON =
  "No se aprueba para consumo downstream hasta corregir la extraccion.";
const DEFAULT_LLAMA_CONTROLS: LlamaControls = {
  providerMode: "local",
  route: DEFAULT_LLAMA_ROUTE,
};

const LOCAL_INGESTION_STEPS = [
  {
    title: "PDF digital",
    body: "pdfplumber lee layout, texto, tablas y formularios; pypdf queda como respaldo de texto.",
  },
  {
    title: "OCR Tesseract",
    body: "pypdfium2 rasteriza paginas o regiones; Tesseract spa extrae texto con confianza por palabra.",
  },
  {
    title: "Hibrido",
    body: "si falta cobertura en el PDF digital, se agrega OCR regional y se conserva la trazabilidad local.",
  },
];

const statusLabels: Record<DisplayStatus, string> = {
  pending: "Pendiente",
  processed: "Procesado",
  failed: "Fallido",
  needs_review: "Needs review",
  approved: "Aprobado",
  rejected: "Rechazado",
};

const viewTitles: Record<AppView, string> = {
  operations: "Operacion de ingesta",
  review: "Revision documental",
  inventory: "Inventario documental",
};

function App() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string>("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [ingestionFilter, setIngestionFilter] = useState("all");
  const [activeView, setActiveView] = useState<AppView>("review");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [lastResult, setLastResult] = useState<ActionResult | null>(null);
  const [llamaControls, setLlamaControls] = useState<LlamaControls>(DEFAULT_LLAMA_CONTROLS);
  const [ocrThresholdInput, setOcrThresholdInput] = useState("80");
  const [uploadForm, setUploadForm] = useState({
    category: "general_sst",
    folder: "manuales",
    file: null as File | null,
  });

  const loadStatus = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/status");
      const payload = await readJson<StatusPayload>(response);
      setStatus(payload);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo cargar estado.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    if (!status?.llamaFirst) return;
    setLlamaControls({
      providerMode: status.llamaFirst.cloudEnabled ? "llama_cloud" : "local",
      route: routeFromStatus(status.llamaFirst),
    });
    setOcrThresholdInput(String(status.settings.ocrReviewThresholdPercent));
  }, [status?.llamaFirst, status?.settings]);

  const ocrThresholdValidation = useMemo(
    () => validateOcrThresholdPercent(ocrThresholdInput),
    [ocrThresholdInput],
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

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!uploadForm.file) {
      setNotice("Selecciona un archivo .pdf o .md.");
      return;
    }
    const body = new FormData();
    body.append("category", uploadForm.category.trim());
    body.append("folder", uploadForm.folder.trim());
    body.append("file", uploadForm.file);
    setBusyAction("upload");
    try {
      const response = await fetch("/api/upload", { method: "POST", body });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setUploadForm((current) => ({ ...current, file: null }));
      setNotice(`Documento cargado: ${payload.sourceRelpath}`);
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo cargar archivo.");
    } finally {
      setBusyAction(null);
    }
  };

  const submitReview = async (document: DocumentRecord, decision: DecisionKind) => {
    const fallback =
      decision === "approved" ? DEFAULT_APPROVE_REASON : DEFAULT_REJECT_REASON;
    const reason = (reviewNotes[document.documentId] || fallback).trim();
    setBusyAction(`${decision}:${document.documentId}`);
    try {
      const response = await fetch(`/api/review/${document.documentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason }),
      });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setNotice(
        `${decision === "approved" ? "Aprobado" : "Rechazado"}: ${document.documentName}`,
      );
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo guardar decision.");
    } finally {
      setBusyAction(null);
    }
  };

  const runPipeline = async () => {
    if (ocrThresholdValidation.status !== "valid") {
      setNotice(ocrThresholdValidation.message);
      return;
    }
    setBusyAction("pipeline");
    try {
      const body = pipelineRequestForControls({
        force: false,
        providerMode: llamaControls.providerMode,
        route: llamaControls.route,
        ocrReviewThresholdPercent: ocrThresholdValidation.value,
      });
      const response = await fetch("/api/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      if (payload.statusPayload) {
        setStatus(payload.statusPayload);
      }
      setNotice(`Ingesta staging finalizada: ${payload.runId}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo ejecutar ingesta.");
    } finally {
      setBusyAction(null);
    }
  };

  const saveSettings = async () => {
    if (ocrThresholdValidation.status !== "valid") {
      setNotice(ocrThresholdValidation.message);
      return;
    }
    setBusyAction("settings");
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ocrReviewThresholdPercent: ocrThresholdValidation.value,
        }),
      });
      const payload = await readJson<{
        ok?: boolean;
        settings?: StatusPayload["settings"];
      }>(response);
      const savedPercent =
        payload.settings?.ocrReviewThresholdPercent ?? ocrThresholdValidation.value;
      setLastResult({ ok: payload.ok, summary: { ocrReviewThresholdPercent: savedPercent } });
      setNotice(`Umbral OCR guardado: ${savedPercent.toFixed(1)}%`);
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo guardar configuracion.");
    } finally {
      setBusyAction(null);
    }
  };

  const runValidation = async () => {
    setBusyAction("validate");
    try {
      const body = lastResult?.stagingRoot
        ? { stagingRoot: lastResult.stagingRoot }
        : undefined;
      const response = await fetch("/api/validate", {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setNotice(
        `Validacion ${payload.target === "staging" ? "staging" : "oficial"} ${payload.status}: ${payload.errors ?? 0} errores.`,
      );
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo validar.");
    } finally {
      setBusyAction(null);
    }
  };

  const promoteStaging = async () => {
    if (!lastResult?.stagingRoot) {
      setNotice("Primero ejecuta y valida una ingesta en staging.");
      return;
    }
    setBusyAction("promote");
    try {
      const response = await fetch("/api/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stagingRoot: lastResult.stagingRoot }),
      });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setNotice(`Staging promovido a salida oficial: ${payload.runId}`);
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo promover staging.");
    } finally {
      setBusyAction(null);
    }
  };

  const selectedDocument =
    documents.find((document) => document.documentId === selectedDocumentId) ??
    pendingReview[0] ??
    filteredDocuments[0] ??
    null;

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onViewChange={setActiveView} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{viewTitles[activeView]}</h1>
            <p>Schema {status?.summary.schemaVersion ?? "2.0"} · {status?.summary.runId ?? "sin run"}</p>
          </div>
          <div className="topbar-actions">
            <div className="view-switcher" aria-label="Cambiar vista">
              <button
                className={activeView === "operations" ? "active" : ""}
                onClick={() => setActiveView("operations")}
                type="button"
              >
                Operacion
              </button>
              <button
                className={activeView === "review" ? "active" : ""}
                onClick={() => setActiveView("review")}
                type="button"
              >
                Revision
              </button>
              <button
                className={activeView === "inventory" ? "active" : ""}
                onClick={() => setActiveView("inventory")}
                type="button"
              >
                Inventario
              </button>
            </div>
            <button className="ghost-button" onClick={loadStatus} disabled={loading}>
              <RefreshCw size={16} />
              Actualizar
            </button>
            <span className="user-chip">Operaciones SST</span>
          </div>
        </header>

        {notice ? <div className="notice">{notice}</div> : null}

        <DashboardSummary summary={status?.summary ?? null} />

        {activeView === "operations" ? (
          <>
            <LlamaStatusPanel
              status={status?.llamaFirst ?? null}
              controls={llamaControls}
              ocrThresholdInput={ocrThresholdInput}
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
                controls={llamaControls}
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

        {activeView === "review" ? (
          <section className="review-workspace">
            <PendingReviewPanel
              documents={pendingReview}
              busyAction={busyAction}
              notes={reviewNotes}
              selectedDocumentId={selectedDocument?.documentId ?? null}
              onSelect={(document) => setSelectedDocumentId(document.documentId)}
              onNoteChange={(documentId, value) =>
                setReviewNotes((current) => ({ ...current, [documentId]: value }))
              }
              onReview={submitReview}
            />
            <DocumentReviewInspector
              document={selectedDocument}
              busyAction={busyAction}
              note={selectedDocument ? reviewNotes[selectedDocument.documentId] ?? "" : ""}
              onNoteChange={(value) => {
                if (selectedDocument) {
                  setReviewNotes((current) => ({
                    ...current,
                    [selectedDocument.documentId]: value,
                  }));
                }
              }}
              onReview={submitReview}
            />
          </section>
        ) : null}

        {activeView === "inventory" ? (
          <section className="inventory-workspace">
            <InventoryPanel
              documents={filteredDocuments}
              total={documents.length}
              query={query}
              statusFilter={statusFilter}
              ingestionFilter={ingestionFilter}
              ingestionMethodOptions={ingestionMethodOptions}
              selectedDocumentId={selectedDocument?.documentId ?? null}
              onSelect={(document) => setSelectedDocumentId(document.documentId)}
              onQueryChange={setQuery}
              onStatusFilterChange={setStatusFilter}
              onIngestionFilterChange={setIngestionFilter}
            />
            <DocumentReviewInspector
              document={selectedDocument}
              busyAction={busyAction}
              note={selectedDocument ? reviewNotes[selectedDocument.documentId] ?? "" : ""}
              onNoteChange={(value) => {
                if (selectedDocument) {
                  setReviewNotes((current) => ({
                    ...current,
                    [selectedDocument.documentId]: value,
                  }));
                }
              }}
              onReview={submitReview}
            />
          </section>
        ) : null}
      </main>
    </div>
  );
}

function LlamaStatusPanel({
  status,
  controls,
  ocrThresholdInput,
  ocrThresholdValidation,
  settingsBusy,
  onControlsChange,
  onOcrThresholdChange,
  onSaveSettings,
}: {
  status: StatusPayload["llamaFirst"] | null;
  controls: LlamaControls;
  ocrThresholdInput: string;
  ocrThresholdValidation: OcrThresholdValidation;
  settingsBusy: boolean;
  onControlsChange: (controls: LlamaControls) => void;
  onOcrThresholdChange: (value: string) => void;
  onSaveSettings: () => void;
}) {
  if (!status) return null;
  const cloudSelected = controls.providerMode === "llama_cloud";
  const selectedRoute = llamaCloudConfigFromRoute(controls.route);
  const selectedRouteLabel =
    LLAMA_ROUTE_OPTIONS.find((option) => option.value === controls.route)?.summary ?? "Parse";
  const orderOptions = matchingRoutesForServices({
    classifyEnabled: selectedRoute.classifyEnabled,
    extractEnabled: selectedRoute.extractEnabled,
  });
  const updateService = (
    service: "classifyEnabled" | "extractEnabled",
    enabled: boolean,
  ) => {
    const nextServices = { ...selectedRoute, [service]: enabled };
    onControlsChange({
      ...controls,
      route: routeForServiceSelection(controls.route, nextServices),
    });
  };
  return (
    <section className="panel llama-status" aria-label="Llama-first">
      <div className="panel-heading">
        <h2>Proveedor de ingesta PDF</h2>
        <span>{cloudSelected ? `Llama seleccionado - ${status.configurationStatus}` : "Local seleccionado"}</span>
      </div>
      <div className={cloudSelected ? "llama-layout cloud" : "llama-layout local"}>
        {cloudSelected ? (
          <div className="llama-status-grid">
            <StatusDatum label="Provider" value={status.provider} />
            <StatusDatum label="Cloud" value={status.cloudEnabled ? "Activo" : "Inactivo"} />
            <StatusDatum label="Tier" value={status.parseTier ?? "n/a"} />
            <StatusDatum label="Version" value={status.parseVersion ?? "n/a"} />
            <StatusDatum label="Classify" value={`${status.classifyMode ?? "FAST"} / ${status.classifyMaxPages ?? 5}p`} />
            <StatusDatum label="Extract" value={`${status.extractTier ?? "cost_effective"} + ${status.extractParseTier ?? "fast"}`} />
          </div>
        ) : null}
        <div className="llama-controls">
          <div className="segmented-control" aria-label="Proveedor de PDF">
            <button
              type="button"
              className={controls.providerMode === "local" ? "active" : ""}
              onClick={() => onControlsChange({ ...controls, providerMode: "local" })}
              title="Usar OCR y librerias locales"
            >
              <HardDrive size={15} />
              Local
            </button>
            <button
              type="button"
              className={cloudSelected ? "active" : ""}
              onClick={() => onControlsChange({ ...controls, providerMode: "llama_cloud" })}
              title="Usar LlamaCloud con LlamaParse obligatorio"
            >
              <Cloud size={15} />
              Llama
            </button>
          </div>
          {cloudSelected ? (
            <div className="llama-route-builder">
              <div className="service-toggle-row" aria-label="Servicios LlamaCloud">
                <ServiceToggle
                  label="Parse"
                  icon={<FileText size={15} />}
                  enabled
                  locked
                />
                <ServiceToggle
                  label="Classify"
                  icon={<ListFilter size={15} />}
                  enabled={selectedRoute.classifyEnabled}
                  onToggle={(enabled) => updateService("classifyEnabled", enabled)}
                />
                <ServiceToggle
                  label="Extract"
                  icon={<Database size={15} />}
                  enabled={selectedRoute.extractEnabled}
                  onToggle={(enabled) => updateService("extractEnabled", enabled)}
                />
              </div>
              <div className="route-option-list" aria-label="Orden permitido LlamaCloud">
                {orderOptions.map((option) => (
                  <button
                    type="button"
                    className={
                      option.value === controls.route
                        ? "route-option active"
                        : "route-option"
                    }
                    key={option.value}
                    aria-pressed={option.value === controls.route}
                    aria-label={`Seleccionar orden ${option.summary}`}
                    onClick={() => onControlsChange({ ...controls, route: option.value })}
                    title={`Seleccionar orden ${option.summary}`}
                  >
                    <span>{option.label}</span>
                    <RouteSteps stops={option.stops} />
                  </button>
                ))}
              </div>
              <div className="route-validity">
                <CheckCircle2 size={15} />
                <span>Orden valido</span>
                <strong>{selectedRouteLabel}</strong>
              </div>
            </div>
          ) : (
            <div className="local-provider-note">
              <HardDrive size={15} />
              <span>Pipeline local con PDF digital, OCR Tesseract y fallback hibrido.</span>
            </div>
          )}
          {!cloudSelected ? (
            <div className="local-stack-list" aria-label="Detalle de ingesta local">
              {LOCAL_INGESTION_STEPS.map((step) => (
                <div className="local-stack-item" key={step.title}>
                  <strong>{step.title}</strong>
                  <span>{step.body}</span>
                </div>
              ))}
            </div>
          ) : null}
          <div className="route-summary">
            <span>Se enviara al iniciar staging</span>
            <strong>{cloudSelected ? selectedRouteLabel : "Local"}</strong>
          </div>
          <div
            className={
              ocrThresholdValidation.status === "valid"
                ? "quality-settings"
                : "quality-settings has-error"
            }
            aria-label="Configuracion de confianza OCR"
          >
            <label>
              <span>
                <SlidersHorizontal size={15} />
                Umbral OCR
              </span>
              <input
                type="number"
                min={0}
                max={100}
                step={0.5}
                value={ocrThresholdInput}
                aria-invalid={ocrThresholdValidation.status !== "valid"}
                aria-describedby={
                  ocrThresholdValidation.status === "valid"
                    ? undefined
                    : "ocr-threshold-error"
                }
                onChange={(event) => onOcrThresholdChange(event.currentTarget.value)}
              />
              {ocrThresholdValidation.status !== "valid" ? (
                <span
                  className="field-alert"
                  id="ocr-threshold-error"
                  role="alert"
                >
                  <AlertCircle size={14} />
                  {ocrThresholdValidation.message}
                </span>
              ) : null}
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={onSaveSettings}
              disabled={settingsBusy || ocrThresholdValidation.status !== "valid"}
              title={
                ocrThresholdValidation.status === "valid"
                  ? "Guardar umbral OCR"
                  : ocrThresholdValidation.message
              }
            >
              {settingsBusy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
              Guardar
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function ServiceToggle({
  label,
  icon,
  enabled,
  locked = false,
  onToggle,
}: {
  label: string;
  icon: JSX.Element;
  enabled: boolean;
  locked?: boolean;
  onToggle?: (enabled: boolean) => void;
}) {
  return (
    <button
      type="button"
      className={[
        "service-toggle",
        enabled ? "active" : "",
        locked ? "locked" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-pressed={enabled}
      onClick={() => {
        if (!locked) onToggle?.(!enabled);
      }}
      title={locked ? "Parse es obligatorio para LlamaCloud" : undefined}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function RouteSteps({ stops }: { stops: LlamaStop[] }) {
  return (
    <span className="route-steps">
      {stops.map((stop, index) => (
        <span className="route-step-fragment" key={`${stop}-${index}`}>
          {index > 0 ? <ArrowRight size={12} /> : null}
          <span className={`route-step ${stop}`}>{serviceLabel(stop)}</span>
        </span>
      ))}
    </span>
  );
}

function serviceLabel(stop: LlamaStop) {
  if (stop === "parse") return "Parse";
  if (stop === "classify") return "Classify";
  return "Extract";
}

function StatusDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-datum">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Sidebar({
  activeView,
  onViewChange,
}: {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}) {
  const items = [
    { label: "Operacion", icon: UploadCloud, view: "operations" as const },
    { label: "Revision", icon: Clock3, view: "review" as const },
    { label: "Inventario", icon: Database, view: "inventory" as const },
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <FileText size={24} />
        <span>SST Pipeline</span>
      </div>
      <nav>
        {items.map((item) => (
          <button
            className={activeView === item.view ? "nav-item active" : "nav-item"}
            key={item.label}
            onClick={() => onViewChange(item.view)}
            type="button"
          >
            <item.icon size={18} />
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}

function MetricCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: JSX.Element;
  tone: "neutral" | "success" | "warning" | "danger";
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value.toLocaleString("es-CO")}</strong>
      </div>
    </article>
  );
}

function UploadPanel({
  categories,
  form,
  busy,
  onChange,
  onSubmit,
}: {
  categories: string[];
  form: { category: string; folder: string; file: File | null };
  busy: boolean;
  onChange: (value: { category: string; folder: string; file: File | null }) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="panel upload-panel">
      <div className="panel-heading">
        <h2>Nuevo documento</h2>
      </div>
      <form onSubmit={onSubmit}>
        <label className="drop-zone">
          <UploadCloud size={32} />
          <span>{form.file ? form.file.name : "Selecciona PDF o Markdown"}</span>
          <small>Formatos .pdf, .md, .markdown</small>
          <input
            type="file"
            accept=".pdf,.md,.markdown"
            onChange={(event) =>
              onChange({ ...form, file: event.currentTarget.files?.[0] ?? null })
            }
          />
        </label>
        <label>
          Categoria
          <select
            value={form.category}
            onChange={(event) => onChange({ ...form, category: event.target.value })}
          >
            {categories.length === 0 ? <option value="general_sst">general_sst</option> : null}
            {categories.map((category) => (
              <option value={category} key={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <label>
          Carpeta destino
          <input
            value={form.folder}
            placeholder="manuales/politica"
            onChange={(event) => onChange({ ...form, folder: event.target.value })}
          />
        </label>
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? <Loader2 className="spin" size={16} /> : <UploadCloud size={16} />}
          Subir documento
        </button>
      </form>
    </section>
  );
}

function PendingReviewPanel({
  documents,
  busyAction,
  notes,
  selectedDocumentId,
  onSelect,
  onNoteChange,
  onReview,
}: {
  documents: DocumentRecord[];
  busyAction: string | null;
  notes: Record<string, string>;
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onNoteChange: (documentId: string, value: string) => void;
  onReview: (document: DocumentRecord, decision: DecisionKind) => void;
}) {
  return (
    <section className="panel review-panel">
      <div className="panel-heading">
        <h2>Pending review</h2>
        <span>{documents.length} pendientes</span>
      </div>
      <div className="table-wrap compact">
        <table>
          <thead>
            <tr>
              <th>Documento</th>
              <th>Categoria</th>
              <th>Motivos</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                key={document.documentId}
              >
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.documentName}</span>
                    <small>{document.sourceRelpath}</small>
                    <button
                      className="row-detail-button"
                      onClick={() => onSelect(document)}
                      type="button"
                    >
                      Ver detalle
                    </button>
                  </div>
                </td>
                <td>{document.category}</td>
                <td>
                  <ReasonList reasons={document.reviewReasons} />
                </td>
                <td className="review-actions">
                  <textarea
                    aria-label={`Motivo para ${document.documentName}`}
                    value={notes[document.documentId] ?? ""}
                    placeholder="Motivo de revision"
                    onChange={(event) => onNoteChange(document.documentId, event.target.value)}
                  />
                  <div>
                    <button
                      className="approve-button"
                      disabled={busyAction === `approved:${document.documentId}`}
                      onClick={() => onReview(document, "approved")}
                    >
                      <Check size={15} />
                      Aprobar
                    </button>
                    <button
                      className="reject-button"
                      disabled={busyAction === `rejected:${document.documentId}`}
                      onClick={() => onReview(document, "rejected")}
                    >
                      <X size={15} />
                      Rechazar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="empty-cell">
                  Sin documentos pendientes de decision.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function InventoryPanel({
  documents,
  total,
  query,
  statusFilter,
  ingestionFilter,
  ingestionMethodOptions,
  selectedDocumentId,
  onSelect,
  onQueryChange,
  onStatusFilterChange,
  onIngestionFilterChange,
}: {
  documents: DocumentRecord[];
  total: number;
  query: string;
  statusFilter: string;
  ingestionFilter: string;
  ingestionMethodOptions: { value: string; label: string }[];
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onIngestionFilterChange: (value: string) => void;
}) {
  return (
    <section className="panel inventory-panel">
      <div className="panel-heading inventory-heading">
        <div>
          <h2>Inventario</h2>
          <span>
            {documents.length} de {total}
          </span>
        </div>
        <div className="inventory-tools">
          <label className="search-field">
            <Search size={16} />
            <input
              value={query}
              placeholder="Buscar documento"
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </label>
          <label className="filter-field">
            <ListFilter size={16} />
            <select
              value={statusFilter}
              onChange={(event) => onStatusFilterChange(event.target.value)}
            >
              <option value="all">Todos</option>
              <option value="processed">Procesados</option>
              <option value="needs_review">Needs review</option>
              <option value="failed">Fallidos</option>
              <option value="approved">Aprobados</option>
              <option value="rejected">Rechazados</option>
            </select>
          </label>
          <label className="filter-field">
            <UploadCloud size={16} />
            <select
              value={ingestionFilter}
              onChange={(event) => onIngestionFilterChange(event.target.value)}
              aria-label="Filtrar por ingesta"
            >
              <option value="all">Toda ingesta</option>
              <optgroup label="Proveedor">
                <option value="provider:local">Local</option>
                <option value="provider:llama_cloud">Llama</option>
                <option value="provider:unregistered">Sin ingesta</option>
              </optgroup>
              {ingestionMethodOptions.length > 0 ? (
                <optgroup label="Metodo">
                  {ingestionMethodOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              ) : null}
            </select>
          </label>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ruta del documento</th>
              <th>Tipo</th>
              <th>Ingesta</th>
              <th>Confiabilidad</th>
              <th>Categoria</th>
              <th>Tamano</th>
              <th>Estado</th>
              <th>Decision de revision</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                key={document.documentId}
              >
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.sourceRelpath}</span>
                    <small>{document.documentId}</small>
                    <button
                      className="row-detail-button"
                      onClick={() => onSelect(document)}
                      type="button"
                    >
                      Revisar evidencia
                    </button>
                  </div>
                </td>
                <td>{document.detectedExtension?.replace(".", "").toUpperCase() ?? "N/D"}</td>
                <td>
                  <IngestionChip document={document} />
                </td>
                <td>
                  <ConfidenceChip document={document} />
                </td>
                <td>{document.category}</td>
                <td>{formatBytes(document.fileSize)}</td>
                <td>
                  <StatusChip status={document.displayStatus} />
                </td>
                <td>
                  <DecisionChip reviewStatus={document.reviewStatus} />
                </td>
                <td>{formatDate(document.ingestionDate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {documents.length === 0 ? (
          <div className="empty-cell">No hay documentos con los filtros actuales.</div>
        ) : null}
      </div>
    </section>
  );
}

function DocumentReviewInspector({
  document,
  busyAction,
  note,
  onNoteChange,
  onReview,
}: {
  document: DocumentRecord | null;
  busyAction: string | null;
  note: string;
  onNoteChange: (value: string) => void;
  onReview: (document: DocumentRecord, decision: DecisionKind) => void;
}) {
  if (!document) {
    return (
      <aside className="panel document-inspector">
        <div className="panel-heading">
          <h2>Detalle de revision</h2>
        </div>
        <div className="inspector-empty">
          <FileText size={28} />
          <span>Selecciona un documento para revisar rutas, motivos y decisiones.</span>
        </div>
      </aside>
    );
  }

  const canReview = document.processingStatus === "needs_review";
  const approveBusy = busyAction === `approved:${document.documentId}`;
  const rejectBusy = busyAction === `rejected:${document.documentId}`;

  return (
    <aside className="panel document-inspector">
      <div className="panel-heading">
        <h2>Detalle de revision</h2>
        <DecisionChip reviewStatus={document.reviewStatus} />
      </div>
      <div className="inspector-body">
        <div className="inspector-title">
          <FileText size={18} />
          <div>
            <strong>{document.documentName}</strong>
            <span>{document.sourceRelpath}</span>
          </div>
        </div>

        <dl className="metadata-grid">
          <div>
            <dt>Document ID</dt>
            <dd>{document.documentId}</dd>
          </div>
          <div>
            <dt>Categoria</dt>
            <dd>{document.category ?? "N/D"}</dd>
          </div>
          <div>
            <dt>Tipo</dt>
            <dd>{document.detectedExtension?.replace(".", "").toUpperCase() ?? "N/D"}</dd>
          </div>
          <div>
            <dt>Tamano</dt>
            <dd>{formatBytes(document.fileSize)}</dd>
          </div>
          <div>
            <dt>Ingesta</dt>
            <dd>{document.ingestionProviderLabel}</dd>
          </div>
          <div>
            <dt>Metodo</dt>
            <dd>{document.ingestionMethodLabel}</dd>
          </div>
          <div>
            <dt>OCR</dt>
            <dd>{document.ocrConfidenceLabel}</dd>
          </div>
          <div>
            <dt>Fecha</dt>
            <dd>{formatDate(document.ingestionDate)}</dd>
          </div>
        </dl>

        <section className="inspector-section">
          <h3>Motivos de mismatch o revision</h3>
          <ReasonList reasons={document.reviewReasons} />
        </section>

        <section className="inspector-section">
          <h3>Detalles auditables</h3>
          {document.reviewDetails.length > 0 ? (
            <ul className="detail-list">
              {document.reviewDetails.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          ) : (
            <span className="muted">Sin detalles adicionales.</span>
          )}
        </section>

        {document.decision ? (
          <section className="decision-summary">
            <h3>Decision registrada</h3>
            <p>{document.decision.reason}</p>
            <small>{formatDate(document.decision.decided_at)}</small>
          </section>
        ) : null}

        {canReview ? (
          <section className="inspector-section">
            <label className="inspector-note">
              Motivo de decision
              <textarea
                aria-label={`Motivo para ${document.documentName}`}
                onChange={(event) => onNoteChange(event.target.value)}
                placeholder="Describe por que se aprueba o se rechaza"
                value={note}
              />
            </label>
            <div className="inspector-actions">
              <button
                className="approve-button"
                disabled={approveBusy || rejectBusy}
                onClick={() => onReview(document, "approved")}
                type="button"
              >
                {approveBusy ? <Loader2 className="spin" size={15} /> : <Check size={15} />}
                Aprobar
              </button>
              <button
                className="reject-button"
                disabled={approveBusy || rejectBusy}
                onClick={() => onReview(document, "rejected")}
                type="button"
              >
                {rejectBusy ? <Loader2 className="spin" size={15} /> : <X size={15} />}
                Rechazar
              </button>
            </div>
          </section>
        ) : (
          <section className="inspector-section">
            <span className="muted">Este documento no requiere decision manual.</span>
          </section>
        )}
      </div>
    </aside>
  );
}

function IngestionChip({ document }: { document: DocumentRecord }) {
  return (
    <div className="ingestion-cell">
      <span className={`chip ingestion-${document.ingestionProvider}`}>
        {document.ingestionProviderLabel}
      </span>
      <small>{document.ingestionMethodLabel}</small>
    </div>
  );
}

function DashboardSummary({ summary }: { summary: StatusPayload["summary"] | null }) {
  return (
    <section className="metric-grid" aria-label="Resumen">
      <MetricCard label="Total" value={summary?.total ?? 0} icon={<FileText />} tone="neutral" />
      <MetricCard label="Procesados" value={summary?.processed ?? 0} icon={<CheckCircle2 />} tone="success" />
      <MetricCard label="Pending review" value={summary?.needsReview ?? 0} icon={<Clock3 />} tone="warning" />
      <MetricCard label="Fallidos" value={summary?.failed ?? 0} icon={<AlertCircle />} tone="danger" />
      <MetricCard label="Aprobados" value={summary?.approved ?? 0} icon={<Check />} tone="success" />
      <MetricCard label="Rechazados" value={summary?.rejected ?? 0} icon={<X />} tone="danger" />
    </section>
  );
}

function ConfidenceChip({ document }: { document: DocumentRecord }) {
  const hasValue = document.ocrConfidencePercent !== null;
  return (
    <div className="confidence-cell">
      <span className={hasValue ? "chip confidence-value" : "chip confidence-na"}>
        {document.ocrConfidenceLabel}
      </span>
      <small>{document.ocrConfidenceKind}</small>
    </div>
  );
}

function PipelinePanel({
  validation,
  lastResult,
  busyAction,
  controls,
  pipelineBlockedReason,
  onRunPipeline,
  onValidate,
  onPromote,
}: {
  validation: StatusPayload["validation"];
  lastResult: ActionResult | null;
  busyAction: string | null;
  controls: LlamaControls;
  pipelineBlockedReason: string | null;
  onRunPipeline: () => void;
  onValidate: () => void;
  onPromote: () => void;
}) {
  const cloudSelected = controls.providerMode === "llama_cloud";
  const selectedRouteLabel =
    LLAMA_ROUTE_OPTIONS.find((option) => option.value === controls.route)?.summary ?? "Parse";
  const pipelineButtonLabel = cloudSelected
    ? `Enviar documentos a LlamaCloud: ${selectedRouteLabel}`
    : "Ejecutar ingesta local en staging";
  const validationButtonLabel = lastResult?.stagingRoot
    ? "Validar staging"
    : "Validar salida oficial";
  const hasStagingCandidate = Boolean(lastResult?.stagingRoot);
  return (
    <section className="pipeline-band">
      <div className="pipeline-actions">
        <div>
          <h2>Acciones del pipeline</h2>
          <div className="button-row">
            <button
              className="primary-button"
              onClick={onRunPipeline}
              disabled={busyAction === "pipeline" || Boolean(pipelineBlockedReason)}
              title={pipelineBlockedReason ?? pipelineButtonLabel}
            >
              {busyAction === "pipeline" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
              {pipelineButtonLabel}
            </button>
            {pipelineBlockedReason ? (
              <span className="pipeline-action-alert" role="alert">
                <AlertCircle size={14} />
                {pipelineBlockedReason}
              </span>
            ) : null}
            <button
              className="secondary-button"
              onClick={onValidate}
              disabled={busyAction === "validate"}
            >
              {busyAction === "validate" ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
              {validationButtonLabel}
            </button>
            <button
              className="secondary-button"
              onClick={onPromote}
              disabled={!hasStagingCandidate || busyAction === "promote"}
            >
              {busyAction === "promote" ? <Loader2 className="spin" size={16} /> : <ArrowRight size={16} />}
              Promover staging
            </button>
          </div>
        </div>
        <div className="validation-summary">
          <span>Validacion</span>
          <strong className={validation?.status === "passed" ? "ok-text" : "warn-text"}>
            {validation?.status ?? "Sin reporte"}
          </strong>
          <small>{validation?.path ?? "data/docs_normalized/_manifests"}</small>
        </div>
      </div>
      {lastResult ? (
        <pre className="result-box">{JSON.stringify(lastResult, null, 2)}</pre>
      ) : null}
    </section>
  );
}

function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return <span className="muted">Sin motivos</span>;
  }
  return (
    <div className="reason-list">
      {reasons.map((reason) => (
        <span key={reason}>{reason}</span>
      ))}
    </div>
  );
}

function StatusChip({ status }: { status: DisplayStatus }) {
  return <span className={`chip status-${status}`}>{statusLabels[status]}</span>;
}

function DecisionChip({ reviewStatus }: { reviewStatus: ReviewStatus }) {
  if (reviewStatus === "not_required") {
    return <span className="chip neutral">No aplica</span>;
  }
  if (reviewStatus === "pending") {
    return <span className="chip neutral">Pendiente</span>;
  }
  return (
    <span className={`chip decision-${reviewStatus}`}>
      {reviewStatus === "approved" ? "Aprobado" : "Rechazado"}
    </span>
  );
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? `HTTP ${response.status}`);
  }
  return payload;
}

function formatBytes(value: number) {
  if (!Number.isFinite(value)) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-CO", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default App;
