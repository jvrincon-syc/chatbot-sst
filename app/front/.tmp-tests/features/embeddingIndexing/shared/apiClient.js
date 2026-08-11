import { readJsonResponse } from "../../../shared/readJsonResponse.js";
function toErrorEnvelope(payload) {
    return payload && typeof payload === "object" ? payload : {};
}
function toPipelineHttpError(response, payload) {
    const envelope = toErrorEnvelope(payload);
    const error = new Error(envelope.error?.message ?? `HTTP ${response.status}`);
    error.status = response.status;
    error.code = envelope.error?.code ?? null;
    error.runId = envelope.error?.run_id ?? null;
    error.details = envelope.error?.details ?? {};
    return error;
}
export async function readJson(response) {
    const payload = await readJsonResponse(response);
    if (!response.ok) {
        throw toPipelineHttpError(response, payload);
    }
    return payload;
}
// Builds a stable snake_case query string. Null and undefined values are
// dropped so callers can pass optional filters without conditional branching.
export function buildQuery(params) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value === null || value === undefined || value === "") {
            continue;
        }
        search.set(key, String(value));
    }
    const query = search.toString();
    return query ? `?${query}` : "";
}
export function createIdempotencyKey(prefix) {
    const cryptoObject = globalThis.crypto;
    if (cryptoObject?.randomUUID) {
        return `${prefix}-${cryptoObject.randomUUID()}`;
    }
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
export function toPaginatedResponse(payload, mapper) {
    return {
        items: Array.isArray(payload.items)
            ? payload.items
                .filter((item) => typeof item === "object" && item !== null)
                .map(mapper)
            : [],
        page: Number(payload.page ?? 1),
        pageSize: Number(payload.page_size ?? 25),
        totalItems: Number(payload.total_items ?? 0),
        totalPages: Number(payload.total_pages ?? 0),
    };
}
export async function getJson(path, options) {
    const response = await fetch(path, { signal: options?.signal });
    return readJson(response);
}
export async function postJson(path, body, options) {
    const headers = {
        "Content-Type": "application/json",
    };
    if (options?.idempotencyKey) {
        headers["Idempotency-Key"] = options.idempotencyKey;
    }
    const response = await fetch(path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: options?.signal,
    });
    return readJson(response);
}
