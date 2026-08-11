export const DEFAULT_APPROVE_REASON = "Revision humana completada; apto para consumo downstream.";
export const DEFAULT_REJECT_REASON = "No se aprueba para consumo downstream hasta corregir la extraccion.";
export const DEFAULT_LLAMA_CONTROLS = {
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
export const statusLabels = {
    pending: "Pendiente",
    processed: "Procesado",
    failed: "Fallido",
    needs_review: "En revision",
    approved: "Aprobado",
    rejected: "Rechazado",
};
export const viewTitles = {
    operations: "Operacion de ingesta",
    review: "Revision documental",
    inventory: "Inventario documental",
    chunking: "Chunking local",
    "embedding-indexing": "Embedding e Indexing",
};
export function createDefaultDashboardPreferences() {
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
