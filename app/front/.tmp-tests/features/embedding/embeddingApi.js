import { buildQuery, createIdempotencyKey, getJson, postJson, toPaginatedResponse, } from "../embeddingIndexing/shared/apiClient.js";
import { toEmbeddingBundleChunk, toEmbeddingBundleSummary, toEmbeddingBundleValidation, toEmbeddingChunkBundleListItem, toEmbeddingChunkBundleSummary, toEmbeddingIndexingReadiness, toEmbeddingProfile, toEmbeddingRun, toEmbeddingRuntimeStatus, } from "./embeddingMappers.js";
function pageQuery(options) {
    return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}
export async function loadEmbeddingProfiles(options) {
    const payload = await getJson(`/api/embedding/profiles${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toEmbeddingProfile);
}
export async function loadEmbeddingRuntime(options) {
    const payload = await getJson(`/api/embedding/runtime${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toEmbeddingRuntimeStatus);
}
export async function loadChunkBundles(options) {
    const payload = await getJson(`/api/embedding/chunk-bundles${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toEmbeddingChunkBundleListItem);
}
export async function loadChunkBundleSummary(chunkBundleId, options) {
    const payload = await getJson(`/api/embedding/chunk-bundles/${encodeURIComponent(chunkBundleId)}/summary`, { signal: options?.signal });
    return toEmbeddingChunkBundleSummary(payload);
}
export async function createEmbeddingRun(request, options) {
    const payload = await postJson("/api/embedding/runs", {
        chunk_bundle_id: request.chunkBundleId,
        profile_id: request.profileId,
    }, {
        idempotencyKey: options.idempotencyKey ?? createIdempotencyKey("embedding"),
        signal: options.signal,
    });
    return toEmbeddingRun(payload);
}
export async function loadEmbeddingRun(embeddingRunId, options) {
    const payload = await getJson(`/api/embedding/runs/${encodeURIComponent(embeddingRunId)}`, { signal: options?.signal });
    return toEmbeddingRun(payload);
}
export async function loadEmbeddingBundle(embeddingBundleId, options) {
    const payload = await getJson(`/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}`, { signal: options?.signal });
    return toEmbeddingBundleSummary(payload);
}
export async function loadEmbeddingBundleChunks(embeddingBundleId, options) {
    const payload = await getJson(`/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/chunks${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toEmbeddingBundleChunk);
}
export async function loadEmbeddingBundleValidation(embeddingBundleId, options) {
    const payload = await getJson(`/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/validation`, { signal: options?.signal });
    return toEmbeddingBundleValidation(payload);
}
export async function loadEmbeddingIndexingReadiness(embeddingBundleId, options) {
    const payload = await getJson(`/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/indexing-readiness`, { signal: options?.signal });
    return toEmbeddingIndexingReadiness(payload);
}
