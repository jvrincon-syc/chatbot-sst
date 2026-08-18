import type { ProviderMode } from "../../pipelineRequest";
import type { LlamaRoute } from "../../llamaRoutes";

export type DecisionKind = "approved" | "rejected";
export type ReviewStatus = "not_required" | "pending" | DecisionKind;
export type ProcessingStatus = "pending" | "processed" | "failed" | "needs_review";
export type DisplayStatus = ProcessingStatus | DecisionKind;
export type AppView =
  | "operations"
  | "review"
  | "inventory"
  | "chunking"
  | "embedding-indexing";

export type LlamaControls = {
  providerMode: ProviderMode;
  route: LlamaRoute;
};

export type DocumentSelectionState = {
  review: string | null;
  inventory: string | null;
};

export type DocumentSelectionView = keyof DocumentSelectionState;

export type EmbeddingIndexingStage =
  | "embedding"
  | "indexing"
  | "activation"
  | "retrieval";

export type EmbeddingIndexingState = {
  activeStage: EmbeddingIndexingStage;
  selectedEmbeddingProfileId: string | null;
  selectedChunkBundleId: string | null;
  activeEmbeddingRunId: string | null;
  selectedEmbeddingBundleId: string | null;
  activeIndexingRunId: string | null;
  activeActivationRunId: string | null;
  selectedRetrievalProfileId: string | null;
};

export type ReviewDecision = {
  document_id: string;
  source_relpath: string;
  decision: DecisionKind;
  reason: string;
  decided_at: string;
};

export type DocumentRecord = {
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

export type StatusPayload = {
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
    llamaControls?: LlamaControls;
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

export type ActionResult = {
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

export type DashboardUploadForm = {
  category: string;
  folder: string;
  file: File | null;
};

export type DashboardPreferences = {
  activeView: AppView;
  selectedDocumentIds: DocumentSelectionState;
  embeddingIndexing: EmbeddingIndexingState;
  llamaControls: LlamaControls;
  ocrThresholdInput: string;
};

export const DEFAULT_APPROVE_REASON =
  "Revision humana completada; apto para consumo downstream.";
export const DEFAULT_REJECT_REASON =
  "No se aprueba para consumo downstream hasta corregir la extraccion.";

export const DEFAULT_LLAMA_CONTROLS: LlamaControls = {
  providerMode: "local",
  route: "classify,parse,extract",
};

export const LOCAL_INGESTION_STEPS = [
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

export const statusLabels: Record<DisplayStatus, string> = {
  pending: "Pendiente",
  processed: "Procesado",
  failed: "Fallido",
  needs_review: "En revision",
  approved: "Aprobado",
  rejected: "Rechazado",
};

export const viewTitles: Record<AppView, string> = {
  operations: "Legacy pipeline - Operacion de ingesta",
  review: "Legacy pipeline - Revision documental",
  inventory: "Legacy pipeline - Inventario documental",
  chunking: "Legacy pipeline - Chunking local",
  "embedding-indexing": "Legacy pipeline - Embedding e Indexing",
};

export function createDefaultDashboardPreferences(): DashboardPreferences {
  return {
    activeView: "review",
    selectedDocumentIds: {
      review: null,
      inventory: null,
    },
    embeddingIndexing: {
      activeStage: "embedding",
      selectedEmbeddingProfileId: null,
      selectedChunkBundleId: null,
      activeEmbeddingRunId: null,
      selectedEmbeddingBundleId: null,
      activeIndexingRunId: null,
      activeActivationRunId: null,
      selectedRetrievalProfileId: null,
    },
    llamaControls: DEFAULT_LLAMA_CONTROLS,
    ocrThresholdInput: "80",
  };
}
