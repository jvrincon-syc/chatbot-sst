import {
  buildQuery,
  createIdempotencyKey,
  getJson,
  postJson,
  toPaginatedResponse,
} from "../../shared/api/apiClient.js";
import type { PageOptions, PaginatedResponse } from "../../shared/api/apiTypes.js";
import {
  activationRequestFrom,
  indexingRunRequestFrom,
  toActivationResult,
  toIndexingOverview,
  toIndexingRetrievalReadiness,
  toIndexingRun,
  toIndexingRunDocument,
  toIndexingRunError,
  toIndexingTarget,
} from "./indexingMappers.js";
import type {
  ActivationRequest,
  ActivationResult,
  IndexingOverview,
  IndexingRetrievalReadiness,
  IndexingRun,
  IndexingRunDocument,
  IndexingRunError,
  IndexingRunRequest,
  IndexingTarget,
} from "./indexingTypes.js";

function pageQuery(options?: PageOptions): string {
  return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}

export async function loadIndexingOverview(options?: {
  signal?: AbortSignal;
}): Promise<IndexingOverview> {
  const payload = await getJson<Record<string, unknown>>("/api/indexing/overview", {
    signal: options?.signal,
  });
  return toIndexingOverview(payload);
}

export async function loadIndexingTargets(
  options?: PageOptions,
): Promise<PaginatedResponse<IndexingTarget>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/indexing/targets${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toIndexingTarget);
}

export async function createIndexingRun(
  request: IndexingRunRequest,
  options: { idempotencyKey?: string; signal?: AbortSignal },
): Promise<IndexingRun> {
  const payload = await postJson<Record<string, unknown>>(
    "/api/indexing/runs",
    indexingRunRequestFrom(request),
    {
      idempotencyKey: options.idempotencyKey ?? createIdempotencyKey("indexing"),
      signal: options.signal,
    },
  );
  return toIndexingRun(payload);
}

export async function loadIndexingRun(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<IndexingRun> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/indexing/runs/${encodeURIComponent(runId)}`,
    { signal: options?.signal },
  );
  return toIndexingRun(payload);
}

export async function loadIndexingRunDocuments(
  runId: string,
  options?: PageOptions,
): Promise<PaginatedResponse<IndexingRunDocument>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/indexing/runs/${encodeURIComponent(runId)}/documents${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toIndexingRunDocument);
}

export async function loadIndexingRunErrors(
  runId: string,
  options?: PageOptions,
): Promise<PaginatedResponse<IndexingRunError>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/indexing/runs/${encodeURIComponent(runId)}/errors${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toIndexingRunError);
}

export async function loadIndexingRetrievalReadiness(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<IndexingRetrievalReadiness> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/indexing/runs/${encodeURIComponent(runId)}/retrieval-readiness`,
    { signal: options?.signal },
  );
  return toIndexingRetrievalReadiness(payload);
}

export async function activateIndexingRun(
  request: ActivationRequest,
  options?: { signal?: AbortSignal },
): Promise<ActivationResult> {
  const payload = await postJson<Record<string, unknown>>(
    "/api/indexing/activations",
    activationRequestFrom(request),
    { signal: options?.signal },
  );
  return toActivationResult(payload);
}
