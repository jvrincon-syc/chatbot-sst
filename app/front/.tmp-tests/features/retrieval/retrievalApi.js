import { buildQuery, getJson, postJson, toPaginatedResponse, } from "../../shared/api/apiClient.js";
import { toRetrievalProfile, toRetrievalProfileStatus, toRetrievalSearchResult, toRetrievalValidationResult, } from "./retrievalMappers.js";
function pageQuery(options) {
    return buildQuery({ page: options?.page ?? null, page_size: options?.pageSize ?? null });
}
export async function loadRetrievalProfiles(options) {
    const payload = await getJson(`/api/retrieval/profiles${pageQuery(options)}`, { signal: options?.signal });
    return toPaginatedResponse(payload, toRetrievalProfile);
}
export async function loadRetrievalProfileStatus(retrievalProfileId, options) {
    const payload = await getJson(`/api/retrieval/profiles/${encodeURIComponent(retrievalProfileId)}/status`, { signal: options?.signal });
    return toRetrievalProfileStatus(payload);
}
// Validation is a separate operator action from activation. The backend uses an
// internal synthetic query; no real user question is ever sent.
export async function validateRetrievalProfile(retrievalProfileId, options) {
    const payload = await postJson("/api/retrieval/validate", { retrieval_profile_id: retrievalProfileId }, { signal: options?.signal });
    return toRetrievalValidationResult(payload);
}
export async function searchRetrieval(request, options) {
    const payload = await postJson("/api/retrieval/search", {
        retrieval_profile_id: request.retrievalProfileId,
        query: request.query,
        top_k: request.topK ?? 5,
    }, { signal: options?.signal });
    return toRetrievalSearchResult(payload);
}
