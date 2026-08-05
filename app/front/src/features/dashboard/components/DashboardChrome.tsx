import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Cloud,
  Database,
  FileText,
  HardDrive,
  ListFilter,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  Clock3,
  XCircle,
} from "lucide-react";
import type { FormEvent } from "react";
import {
  LLAMA_ROUTE_OPTIONS,
  llamaCloudConfigFromRoute,
  matchingRoutesForServices,
  routeForServiceSelection,
  type LlamaStop,
} from "../../../llamaRoutes.js";
import type { OcrThresholdValidation } from "../../../ocrSettings";
import type {
  ActionResult,
  AppView,
  DashboardUploadForm,
  LlamaControls,
  StatusPayload,
} from "../dashboardTypes.js";
import { LOCAL_INGESTION_STEPS } from "../dashboardTypes.js";

type NoticeTone = "info" | "success" | "warning" | "danger";

export function DashboardSidebar({
  activeView,
  onViewChange,
}: {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}) {
  const items = [
    { label: "Operación", icon: UploadCloud, view: "operations" as const },
    { label: "Revisión", icon: Clock3, view: "review" as const },
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

export function DashboardNotice({
  tone,
  message,
}: {
  tone: NoticeTone;
  message: string;
}) {
  const icon =
    tone === "success" ? (
      <CheckCircle2 size={16} />
    ) : tone === "warning" ? (
      <AlertCircle size={16} />
    ) : tone === "danger" ? (
      <XCircle size={16} />
    ) : (
      <RefreshCw size={16} />
    );

  return (
    <div className={`notice notice-${tone}`} role="status">
      {icon}
      <span>{message}</span>
    </div>
  );
}

export function DashboardSummary({ summary }: { summary: StatusPayload["summary"] | null }) {
  return (
    <section className="metric-grid" aria-label="Resumen">
      <MetricCard label="Total" value={summary?.total ?? 0} icon={<FileText />} tone="neutral" />
      <MetricCard
        label="Procesados"
        value={summary?.processed ?? 0}
        icon={<CheckCircle2 />}
        tone="success"
      />
      <MetricCard
        label="En revisión"
        value={summary?.needsReview ?? 0}
        icon={<Clock3 />}
        tone="warning"
      />
      <MetricCard label="Fallidos" value={summary?.failed ?? 0} icon={<XCircle />} tone="danger" />
      <MetricCard label="Aprobados" value={summary?.approved ?? 0} icon={<Check />} tone="success" />
      <MetricCard label="Rechazados" value={summary?.rejected ?? 0} icon={<XCircle />} tone="danger" />
    </section>
  );
}

export function LlamaStatusPanel({
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
            <StatusDatum label="Proveedor" value={status.provider} />
            <StatusDatum label="Cloud" value={status.cloudEnabled ? "Activo" : "Inactivo"} />
            <StatusDatum label="Tier" value={status.parseTier ?? "n/a"} />
            <StatusDatum label="Versión" value={status.parseVersion ?? "n/a"} />
            <StatusDatum
              label="Classify"
              value={`${status.classifyMode ?? "FAST"} / ${status.classifyMaxPages ?? 5}p`}
            />
            <StatusDatum
              label="Extract"
              value={`${status.extractTier ?? "cost_effective"} + ${status.extractParseTier ?? "fast"}`}
            />
          </div>
        ) : null}
        <div className="llama-controls">
          <div className="segmented-control" aria-label="Proveedor de PDF">
            <button
              type="button"
              className={controls.providerMode === "local" ? "active" : ""}
              onClick={() => onControlsChange({ ...controls, providerMode: "local" })}
              title="Usar OCR y librerías locales"
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
                <ServiceToggle label="Parse" icon={<FileText size={15} />} enabled locked />
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
                    className={option.value === controls.route ? "route-option active" : "route-option"}
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
                <span>Orden válido</span>
                <strong>{selectedRouteLabel}</strong>
              </div>
            </div>
          ) : (
            <div className="local-provider-note">
              <HardDrive size={15} />
              <span>Pipeline local con PDF digital, OCR Tesseract y fallback híbrido.</span>
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
            <span>Se enviará al iniciar staging</span>
            <strong>{cloudSelected ? selectedRouteLabel : "Local"}</strong>
          </div>
          <div
            className={
              ocrThresholdValidation.status === "valid"
                ? "quality-settings"
                : "quality-settings has-error"
            }
            aria-label="Configuración de confianza OCR"
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
                <span className="field-alert" id="ocr-threshold-error" role="alert">
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
                  ? "Guardar ajustes del proveedor y del OCR"
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

export function UploadPanel({
  categories,
  form,
  busy,
  onChange,
  onSubmit,
}: {
  categories: string[];
  form: DashboardUploadForm;
  busy: boolean;
  onChange: (value: DashboardUploadForm) => void;
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
          Categoría
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

export function PipelinePanel({
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
              {busyAction === "pipeline" ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <Play size={16} />
              )}
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
              {busyAction === "validate" ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <ShieldCheck size={16} />
              )}
              {validationButtonLabel}
            </button>
            <button
              className="secondary-button"
              onClick={onPromote}
              disabled={!hasStagingCandidate || busyAction === "promote"}
            >
              {busyAction === "promote" ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <ArrowRight size={16} />
              )}
              Promover staging
            </button>
          </div>
        </div>
        <div className="validation-summary">
          <span>Validación</span>
          <strong className={validation?.status === "passed" ? "ok-text" : "warn-text"}>
            {validation?.status ?? "Sin reporte"}
          </strong>
          <small>{validation?.path ?? "data/docs_normalized/_manifests"}</small>
        </div>
      </div>
      {lastResult ? <pre className="result-box">{JSON.stringify(lastResult, null, 2)}</pre> : null}
    </section>
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
