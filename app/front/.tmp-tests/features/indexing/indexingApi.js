import { buildQuery, createIdempotencyKey, getJson, postJson, toPaginatedResponse, } from "../embeddingIndexing/shared/apiClient.js";
import { activationRequestFrom, indexingRunRequestFrom, toActivationResult, toIndexingOverview, toIndexingRetrievalReadiness, toIndexingRun, toIndexingRunDocument, toIndexingRunError, toIndexingTarget, } from "./indexingMappers.js";
function pageQuery(options) {
    return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}
export async function loadIndexingOverview(options) {
    const payload = await getJson("/api/indexing/overview", {
        signal: options?.signal,
    });
    return toIndexingOverview(payload);
}
export async function loadIndexingTargets(options) {
    const payload = await getJson(`/api/indexing/targets${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toIndexingTarget);
}
export async function createIndexingRun(request, options) {
    const payload = await postJson("/api/indexing/runs", indexingRunRequestFrom(request), {
        idempotencyKey: options.idempotencyKey ?? createIdempotencyKey("indexing"),
        signal: options.signal,
    });
    return toIndexingRun(payload);
}
export async function loadIndexingRun(runId, options) {
    const payload = await getJson(`/api/indexing/runs/${encodeURIComponent(runId)}`, { signal: options?.signal });
    return toIndexingRun(payload);
}
export async function loadIndexingRunDocuments(runId, options) {
    const payload = await getJson(`/api/indexing/runs/${encodeURIComponent(runId)}/documents${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toIndexingRunDocument);
}
export async function loadIndexingRunErrors(runId, options) {
    const payload = await getJson(`/api/indexing/runs/${encodeURIComponent(runId)}/errors${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toIndexingRunError);
}
export async function loadIndexingRetrievalReadiness(runId, options) {
    const payload = await getJson(`/api/indexing/runs/${encodeURIComponent(runId)}/retrieval-readiness`, { signal: options?.signal });
    return toIndexingRetrievalReadiness(payload);
}
export async function activateIndexingRun(request, options) {
    const payload = await postJson("/api/indexing/activations", activationRequestFrom(request), { signal: options?.signal });
    return toActivationResult(payload);
}
