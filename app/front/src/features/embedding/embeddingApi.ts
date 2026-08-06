import {
  buildQuery,
  createIdempotencyKey,
  getJson,
  postJson,
  toPaginatedResponse,
} from "../embeddingIndexing/shared/apiClient.js";
import type { PageOptions, PaginatedResponse } from "../embeddingIndexing/shared/apiTypes.js";
import {
  toEmbeddingBundleChunk,
  toEmbeddingBundleSummary,
  toEmbeddingBundleValidation,
  toEmbeddingChunkBundleListItem,
  toEmbeddingChunkBundleSummary,
  toEmbeddingIndexingReadiness,
  toEmbeddingProfile,
  toEmbeddingRun,
  toEmbeddingRuntimeStatus,
} from "./embeddingMappers.js";
import type {
  EmbeddingBundleChunk,
  EmbeddingBundleSummary,
  EmbeddingBundleValidation,
  EmbeddingChunkBundleListItem,
  EmbeddingChunkBundleSummary,
  EmbeddingIndexingReadiness,
  EmbeddingProfile,
  EmbeddingRun,
  EmbeddingRunRequest,
  EmbeddingRuntimeStatus,
} from "./embeddingTypes.js";

function pageQuery(options?: PageOptions): string {
  return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}

export async function loadEmbeddingProfiles(
  options?: PageOptions,
): Promise<PaginatedResponse<EmbeddingProfile>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/profiles${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toEmbeddingProfile);
}

export async function loadEmbeddingRuntime(
  options?: PageOptions,
): Promise<PaginatedResponse<EmbeddingRuntimeStatus>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/runtime${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toEmbeddingRuntimeStatus);
}

export async function loadChunkBundles(
  options?: PageOptions,
): Promise<PaginatedResponse<EmbeddingChunkBundleListItem>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/chunk-bundles${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toEmbeddingChunkBundleListItem);
}

export async function loadChunkBundleSummary(
  chunkBundleId: string,
  options?: { signal?: AbortSignal },
): Promise<EmbeddingChunkBundleSummary> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/chunk-bundles/${encodeURIComponent(chunkBundleId)}/summary`,
    { signal: options?.signal },
  );
  return toEmbeddingChunkBundleSummary(payload);
}

export async function createEmbeddingRun(
  request: EmbeddingRunRequest,
  options: { idempotencyKey?: string; signal?: AbortSignal },
): Promise<EmbeddingRun> {
  const payload = await postJson<Record<string, unknown>>(
    "/api/embedding/runs",
    {
      chunk_bundle_id: request.chunkBundleId,
      profile_id: request.profileId,
    },
    {
      idempotencyKey: options.idempotencyKey ?? createIdempotencyKey("embedding"),
      signal: options.signal,
    },
  );
  return toEmbeddingRun(payload);
}

export async function loadEmbeddingRun(
  embeddingRunId: string,
  options?: { signal?: AbortSignal },
): Promise<EmbeddingRun> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/runs/${encodeURIComponent(embeddingRunId)}`,
    { signal: options?.signal },
  );
  return toEmbeddingRun(payload);
}

export async function loadEmbeddingBundle(
  embeddingBundleId: string,
  options?: { signal?: AbortSignal },
): Promise<EmbeddingBundleSummary> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}`,
    { signal: options?.signal },
  );
  return toEmbeddingBundleSummary(payload);
}

export async function loadEmbeddingBundleChunks(
  embeddingBundleId: string,
  options?: PageOptions,
): Promise<PaginatedResponse<EmbeddingBundleChunk>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/chunks${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toEmbeddingBundleChunk);
}

export async function loadEmbeddingBundleValidation(
  embeddingBundleId: string,
  options?: { signal?: AbortSignal },
): Promise<EmbeddingBundleValidation> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/validation`,
    { signal: options?.signal },
  );
  return toEmbeddingBundleValidation(payload);
}

export async function loadEmbeddingIndexingReadiness(
  embeddingBundleId: string,
  options?: { signal?: AbortSignal },
): Promise<EmbeddingIndexingReadiness> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/embedding/bundles/${encodeURIComponent(embeddingBundleId)}/indexing-readiness`,
    { signal: options?.signal },
  );
  return toEmbeddingIndexingReadiness(payload);
}
