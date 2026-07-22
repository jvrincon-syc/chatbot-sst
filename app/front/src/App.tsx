import {
  AlertCircle,
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
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type DecisionKind = "approved" | "rejected";
type ProviderMode = "local" | "llama_cloud";

type LlamaControls = {
  providerMode: ProviderMode;
  classifyEnabled: boolean;
  extractEnabled: boolean;
  callOrder: string;
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
  processingStatus: "pending" | "processed" | "failed" | "needs_review";
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
    parseMaxCreditsPerRun?: number;
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
  summary?: Record<string, number>;
  errors?: number;
  sourceRelpath?: string;
  error?: string;
};

const DEFAULT_APPROVE_REASON =
  "Revision humana completada; apto para consumo downstream.";
const DEFAULT_REJECT_REASON =
  "No se aprueba para consumo downstream hasta corregir la extraccion.";
const DEFAULT_LLAMA_CONTROLS: LlamaControls = {
  providerMode: "local",
  classifyEnabled: true,
  extractEnabled: true,
  callOrder: "classify,parse,extract",
};

const LLAMA_CALL_ORDER_OPTIONS = [
  { value: "classify,parse,extract", label: "Classify > Parse > Extract" },
  { value: "parse,classify,extract", label: "Parse > Classify > Extract" },
];

function effectiveLlamaCallOrder(controls: LlamaControls) {
  if (controls.providerMode !== "llama_cloud") return "parse";
  return controls.callOrder
    .split(",")
    .filter((stop) => {
      if (stop === "parse") return true;
      if (stop === "classify") return controls.classifyEnabled;
      if (stop === "extract") return controls.extractEnabled;
      return false;
    })
    .join(",");
}

const statusLabels: Record<DocumentRecord["processingStatus"], string> = {
  pending: "Pendiente",
  processed: "Procesado",
  failed: "Fallido",
  needs_review: "Needs review",
};

function App() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string>("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [lastResult, setLastResult] = useState<ActionResult | null>(null);
  const [llamaControls, setLlamaControls] = useState<LlamaControls>(DEFAULT_LLAMA_CONTROLS);
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
    const configuredOrder = (status.llamaFirst.callOrder ?? ["classify", "parse", "extract"]).join(",");
    const selectableOrder = LLAMA_CALL_ORDER_OPTIONS.some(
      (option) => option.value === configuredOrder,
    )
      ? configuredOrder
      : DEFAULT_LLAMA_CONTROLS.callOrder;
    setLlamaControls({
      providerMode: status.llamaFirst.cloudEnabled ? "llama_cloud" : "local",
      classifyEnabled: status.llamaFirst.classifyEnabled ?? true,
      extractEnabled: status.llamaFirst.extractEnabled ?? true,
      callOrder: selectableOrder,
    });
  }, [status?.llamaFirst]);

  const documents = status?.documents ?? [];
  const pendingReview = status?.needsReview ?? [];

  const categories = useMemo(() => {
    return Array.from(
      new Set(documents.map((document) => document.category).filter(Boolean)),
    ).sort() as string[];
  }, [documents]);

  const filteredDocuments = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return documents.filter((document) => {
      const matchesQuery =
        !needle ||
        document.sourceRelpath.toLowerCase().includes(needle) ||
        document.documentId.toLowerCase().includes(needle) ||
        document.documentName.toLowerCase().includes(needle);
      const matchesStatus =
        statusFilter === "all" ||
        document.processingStatus === statusFilter ||
        document.decision?.decision === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [documents, query, statusFilter]);

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
    setBusyAction("pipeline");
    try {
      const response = await fetch("/api/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          force: false,
          providerMode: llamaControls.providerMode,
          llamaCloud: {
            classifyEnabled: llamaControls.classifyEnabled,
            extractEnabled: llamaControls.extractEnabled,
            callOrder: effectiveLlamaCallOrder(llamaControls),
          },
        }),
      });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setNotice(`Ingesta staging finalizada: ${payload.runId}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo ejecutar ingesta.");
    } finally {
      setBusyAction(null);
    }
  };

  const runValidation = async () => {
    setBusyAction("validate");
    try {
      const response = await fetch("/api/validate", { method: "POST" });
      const payload = await readJson<ActionResult>(response);
      setLastResult(payload);
      setNotice(`Validacion ${payload.status}: ${payload.errors ?? 0} errores.`);
      await loadStatus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo validar.");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>Ingesta Fase 1</h1>
            <p>Schema {status?.summary.schemaVersion ?? "2.0"} · {status?.summary.runId ?? "sin run"}</p>
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" onClick={loadStatus} disabled={loading}>
              <RefreshCw size={16} />
              Actualizar
            </button>
            <span className="user-chip">Operaciones SST</span>
          </div>
        </header>

        {notice ? <div className="notice">{notice}</div> : null}

        <section className="metric-grid" aria-label="Resumen">
          <MetricCard label="Total" value={status?.summary.total ?? 0} icon={<FileText />} tone="neutral" />
          <MetricCard label="Procesados" value={status?.summary.processed ?? 0} icon={<CheckCircle2 />} tone="success" />
          <MetricCard label="Pending review" value={status?.summary.needsReview ?? 0} icon={<Clock3 />} tone="warning" />
          <MetricCard label="Fallidos" value={status?.summary.failed ?? 0} icon={<AlertCircle />} tone="danger" />
          <MetricCard label="Aprobados" value={status?.summary.approved ?? 0} icon={<Check />} tone="success" />
          <MetricCard label="Rechazados" value={status?.summary.rejected ?? 0} icon={<X />} tone="danger" />
        </section>

        <LlamaStatusPanel
          status={status?.llamaFirst ?? null}
          controls={llamaControls}
          onControlsChange={setLlamaControls}
        />

        <section className="primary-grid">
          <UploadPanel
            categories={categories}
            form={uploadForm}
            busy={busyAction === "upload"}
            onChange={setUploadForm}
            onSubmit={handleUpload}
          />
          <PendingReviewPanel
            documents={pendingReview}
            busyAction={busyAction}
            notes={reviewNotes}
            onNoteChange={(documentId, value) =>
              setReviewNotes((current) => ({ ...current, [documentId]: value }))
            }
            onReview={submitReview}
          />
        </section>

        <InventoryPanel
          documents={filteredDocuments}
          total={documents.length}
          query={query}
          statusFilter={statusFilter}
          onQueryChange={setQuery}
          onStatusFilterChange={setStatusFilter}
        />

        <PipelinePanel
          validation={status?.validation ?? null}
          lastResult={lastResult}
          busyAction={busyAction}
          onRunPipeline={runPipeline}
          onValidate={runValidation}
        />
      </main>
    </div>
  );
}

function LlamaStatusPanel({
  status,
  controls,
  onControlsChange,
}: {
  status: StatusPayload["llamaFirst"] | null;
  controls: LlamaControls;
  onControlsChange: (controls: LlamaControls) => void;
}) {
  if (!status) return null;
  const cloudSelected = controls.providerMode === "llama_cloud";
  return (
    <section className="panel llama-status" aria-label="Llama-first">
      <div className="panel-heading">
        <h2>Llama-first</h2>
        <span>{status.configurationStatus}</span>
      </div>
      <div className="llama-layout">
        <div className="llama-status-grid">
          <StatusDatum label="Provider" value={status.provider} />
          <StatusDatum label="Cloud" value={status.cloudEnabled ? "Activo" : "Inactivo"} />
          <StatusDatum label="Tier" value={status.parseTier ?? "n/a"} />
          <StatusDatum label="Version" value={status.parseVersion ?? "n/a"} />
          <StatusDatum label="Classify" value={`${status.classifyMode ?? "FAST"} / ${status.classifyMaxPages ?? 5}p`} />
          <StatusDatum label="Extract" value={`${status.extractTier ?? "cost_effective"} + ${status.extractParseTier ?? "fast"}`} />
          <StatusDatum label="Creditos" value={String(status.parseMaxCreditsPerRun ?? 0)} />
        </div>
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
              LlamaCloud
            </button>
          </div>
          <label className="toggle-row locked">
            <input type="checkbox" checked={cloudSelected} disabled />
            <span>LlamaParse</span>
          </label>
          <label className={!cloudSelected ? "toggle-row disabled" : "toggle-row"}>
            <input
              type="checkbox"
              checked={controls.classifyEnabled && cloudSelected}
              disabled={!cloudSelected}
              onChange={(event) =>
                onControlsChange({ ...controls, classifyEnabled: event.target.checked })
              }
            />
            <span>LlamaClassify</span>
          </label>
          <label className={!cloudSelected ? "toggle-row disabled" : "toggle-row"}>
            <input
              type="checkbox"
              checked={controls.extractEnabled && cloudSelected}
              disabled={!cloudSelected}
              onChange={(event) =>
                onControlsChange({ ...controls, extractEnabled: event.target.checked })
              }
            />
            <span>LlamaExtract</span>
          </label>
          <label className="order-field">
            Orden
            <select
              value={controls.callOrder}
              disabled={!cloudSelected}
              onChange={(event) => onControlsChange({ ...controls, callOrder: event.target.value })}
            >
              {LLAMA_CALL_ORDER_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </section>
  );
}

function StatusDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-datum">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Sidebar() {
  const items = [
    { label: "Ingesta Fase 1", icon: UploadCloud, active: true },
    { label: "Inventario", icon: Database },
    { label: "Pending review", icon: Clock3 },
    { label: "Manifiestos", icon: FolderOpen },
    { label: "Validaciones", icon: ShieldCheck },
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <FileText size={24} />
        <span>SST Pipeline</span>
      </div>
      <nav>
        {items.map((item) => (
          <button className={item.active ? "nav-item active" : "nav-item"} key={item.label}>
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
  onNoteChange,
  onReview,
}: {
  documents: DocumentRecord[];
  busyAction: string | null;
  notes: Record<string, string>;
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
            {documents.slice(0, 6).map((document) => (
              <tr key={document.documentId}>
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.documentName}</span>
                    <small>{document.sourceRelpath}</small>
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
  onQueryChange,
  onStatusFilterChange,
}: {
  documents: DocumentRecord[];
  total: number;
  query: string;
  statusFilter: string;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
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
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ruta del documento</th>
              <th>Tipo</th>
              <th>Categoria</th>
              <th>Tamano</th>
              <th>Estado</th>
              <th>Decision de revision</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.documentId}>
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.sourceRelpath}</span>
                    <small>{document.documentId}</small>
                  </div>
                </td>
                <td>{document.detectedExtension?.replace(".", "").toUpperCase() ?? "N/D"}</td>
                <td>{document.category}</td>
                <td>{formatBytes(document.fileSize)}</td>
                <td>
                  <StatusChip status={document.processingStatus} />
                </td>
                <td>
                  <DecisionChip decision={document.decision?.decision ?? null} />
                </td>
                <td>{formatDate(document.ingestionDate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PipelinePanel({
  validation,
  lastResult,
  busyAction,
  onRunPipeline,
  onValidate,
}: {
  validation: StatusPayload["validation"];
  lastResult: ActionResult | null;
  busyAction: string | null;
  onRunPipeline: () => void;
  onValidate: () => void;
}) {
  return (
    <section className="pipeline-band">
      <div className="pipeline-actions">
        <div>
          <h2>Acciones del pipeline</h2>
          <div className="button-row">
            <button
              className="primary-button"
              onClick={onRunPipeline}
              disabled={busyAction === "pipeline"}
            >
              {busyAction === "pipeline" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
              Ejecutar ingesta en staging
            </button>
            <button
              className="secondary-button"
              onClick={onValidate}
              disabled={busyAction === "validate"}
            >
              {busyAction === "validate" ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
              Validar salida oficial
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

function StatusChip({ status }: { status: DocumentRecord["processingStatus"] }) {
  return <span className={`chip status-${status}`}>{statusLabels[status]}</span>;
}

function DecisionChip({ decision }: { decision: DecisionKind | null }) {
  if (!decision) {
    return <span className="chip neutral">Pendiente</span>;
  }
  return (
    <span className={`chip decision-${decision}`}>
      {decision === "approved" ? "Aprobado" : "Rechazado"}
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
