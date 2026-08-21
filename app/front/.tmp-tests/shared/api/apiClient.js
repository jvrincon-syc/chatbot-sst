import { readJsonResponse } from "../readJsonResponse.js";
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
// Same-origin auth: the operator session travels as an HttpOnly cookie (Gate 3),
// never a bearer in JS. `same-origin` is the fetch default, set explicitly so the
// cookie contract is visible at the call site.
const CREDENTIALS = "same-origin";
export async function getJson(path, options) {
    const response = await fetch(path, { credentials: CREDENTIALS, signal: options?.signal });
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
        credentials: CREDENTIALS,
        signal: options?.signal,
    });
    return readJson(response);
}
export async function patchJson(path, body, options) {
    const headers = {
        "Content-Type": "application/json",
    };
    if (options?.idempotencyKey) {
        headers["Idempotency-Key"] = options.idempotencyKey;
    }
    const response = await fetch(path, {
        method: "PATCH",
        headers,
        body: JSON.stringify(body),
        credentials: CREDENTIALS,
        signal: options?.signal,
    });
    return readJson(response);
}
// Multipart upload: the browser sets the multipart boundary Content-Type from the
// FormData, so we must NOT set it by hand (a manual header omits the boundary).
export async function postMultipart(path, form, options) {
    const headers = {};
    if (options?.idempotencyKey) {
        headers["Idempotency-Key"] = options.idempotencyKey;
    }
    const response = await fetch(path, {
        method: "POST",
        headers,
        body: form,
        credentials: CREDENTIALS,
        signal: options?.signal,
    });
    return readJson(response);
}
