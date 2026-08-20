import {
  buildQuery,
  getJson,
  postJson,
  toPaginatedResponse,
} from "../../shared/api/apiClient.js";
import type { PageOptions, PaginatedResponse } from "../../shared/api/apiTypes.js";
import {
  toRetrievalProfile,
  toRetrievalProfileStatus,
  toRetrievalSearchResult,
  toRetrievalValidationResult,
} from "./retrievalMappers.js";
import type {
  RetrievalSearchResult,
  RetrievalProfile,
  RetrievalProfileStatus,
  RetrievalValidationResult,
} from "./retrievalTypes.js";

function pageQuery(options?: PageOptions): string {
  return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}

export async function loadRetrievalProfiles(
  options?: PageOptions,
): Promise<PaginatedResponse<RetrievalProfile>> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/retrieval/profiles${pageQuery(options)}`,
    { signal: options?.signal },
  );
  return toPaginatedResponse(payload, toRetrievalProfile);
}

export async function loadRetrievalProfileStatus(
  retrievalProfileId: string,
  options?: { signal?: AbortSignal },
): Promise<RetrievalProfileStatus> {
  const payload = await getJson<Record<string, unknown>>(
    `/api/retrieval/profiles/${encodeURIComponent(retrievalProfileId)}/status`,
    { signal: options?.signal },
  );
  return toRetrievalProfileStatus(payload);
}

// Validation is a separate operator action from activation. The backend uses an
// internal synthetic query; no real user question is ever sent.
export async function validateRetrievalProfile(
  retrievalProfileId: string,
  options?: { signal?: AbortSignal },
): Promise<RetrievalValidationResult> {
  const payload = await postJson<Record<string, unknown>>(
    "/api/retrieval/validate",
    { retrieval_profile_id: retrievalProfileId },
    { signal: options?.signal },
  );
  return toRetrievalValidationResult(payload);
}

export async function searchRetrieval(
  request: {
    retrievalProfileId: string;
    query: string;
    topK?: number;
  },
  options?: { signal?: AbortSignal },
): Promise<RetrievalSearchResult> {
  const payload = await postJson<Record<string, unknown>>(
    "/api/retrieval/search",
    {
      retrieval_profile_id: request.retrievalProfileId,
      query: request.query,
      top_k: request.topK ?? 5,
    },
    { signal: options?.signal },
  );
  return toRetrievalSearchResult(payload);
}
