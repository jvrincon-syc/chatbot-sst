const UNKNOWN_ERROR_CODE = "PIPELINE_UNKNOWN_ERROR";
const UNKNOWN_ERROR_MESSAGE = "Ocurrio un error inesperado en el pipeline.";
// Codes the operator can safely retry without changing the request. Busy and
// transient-availability codes are retryable; contract or state conflicts are not.
const RETRYABLE_CODES = new Set([
    "EMBEDDING_EXECUTOR_BUSY",
    "INDEXING_EXECUTOR_BUSY",
    "EMBEDDING_ENGINE_UNAVAILABLE",
    "POSTGRES_UNAVAILABLE",
    "PGVECTOR_UNAVAILABLE",
]);
export function isPipelineHttpError(error) {
    return error instanceof Error && typeof error.status === "number";
}
function toNullableString(value) {
    return typeof value === "string" && value.length > 0 ? value : null;
}
function toDetails(value) {
    return value && typeof value === "object" ? value : {};
}
export function mapPipelineError(error) {
    if (isPipelineHttpError(error)) {
        const code = error.code ?? UNKNOWN_ERROR_CODE;
        return {
            status: error.status,
            code,
            message: error.message || UNKNOWN_ERROR_MESSAGE,
            runId: error.runId ?? null,
            details: error.details ?? {},
            retryable: isRetryableCode(code, error.status),
        };
    }
    if (error && typeof error === "object") {
        const raw = error;
        const status = typeof raw.status === "number" ? raw.status : null;
        const code = toNullableString(raw.code) ?? UNKNOWN_ERROR_CODE;
        const message = toNullableString(raw.message) ??
            (error instanceof Error ? error.message : null) ??
            UNKNOWN_ERROR_MESSAGE;
        const runId = toNullableString(raw.runId) ?? toNullableString(raw.run_id);
        const retryable = typeof raw.retryable === "boolean" ? raw.retryable : isRetryableCode(code, status);
        return {
            status,
            code,
            message,
            runId,
            details: toDetails(raw.details),
            retryable,
        };
    }
    return {
        status: null,
        code: UNKNOWN_ERROR_CODE,
        message: typeof error === "string" && error ? error : UNKNOWN_ERROR_MESSAGE,
        runId: null,
        details: {},
        retryable: false,
    };
}
function isRetryableCode(code, status) {
    if (RETRYABLE_CODES.has(code)) {
        return true;
    }
    return status === 429 || status === 503;
}
