import type {
  ApiErrorEnvelope,
  PaginatedResponse,
  PipelineHttpError,
} from "./apiTypes.js";
import { readJsonResponse } from "../../../shared/readJsonResponse.js";

function toErrorEnvelope(payload: unknown): ApiErrorEnvelope {
  return payload && typeof payload === "object" ? (payload as ApiErrorEnvelope) : {};
}

function toPipelineHttpError(response: Response, payload: unknown): PipelineHttpError {
  const envelope = toErrorEnvelope(payload);
  const error = new Error(envelope.error?.message ?? `HTTP ${response.status}`) as PipelineHttpError;
  error.status = response.status;
  error.code = envelope.error?.code ?? null;
  error.runId = envelope.error?.run_id ?? null;
  error.details = envelope.error?.details ?? {};
  return error;
}

export async function readJson<T>(response: Response): Promise<T> {
  const payload = await readJsonResponse<unknown>(response);
  if (!response.ok) {
    throw toPipelineHttpError(response, payload);
  }
  return payload as T;
}

// Builds a stable snake_case query string. Null and undefined values are
// dropped so callers can pass optional filters without conditional branching.
export function buildQuery(params: Record<string, string | number | null | undefined>): string {
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

export function createIdempotencyKey(prefix: "embedding" | "indexing"): string {
  const cryptoObject = globalThis.crypto as Crypto | undefined;
  if (cryptoObject?.randomUUID) {
    return `${prefix}-${cryptoObject.randomUUID()}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function toPaginatedResponse<T>(
  payload: Record<string, unknown>,
  mapper: (item: Record<string, unknown>) => T,
): PaginatedResponse<T> {
  return {
    items: Array.isArray(payload.items)
      ? payload.items
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map(mapper)
      : [],
    page: Number(payload.page ?? 1),
    pageSize: Number(payload.page_size ?? 25),
    totalItems: Number(payload.total_items ?? 0),
    totalPages: Number(payload.total_pages ?? 0),
  };
}

export type PipelineGetOptions = {
  signal?: AbortSignal;
};

export async function getJson<T>(path: string, options?: PipelineGetOptions): Promise<T> {
  const response = await fetch(path, { signal: options?.signal });
  return readJson<T>(response);
}

export type PipelinePostOptions = {
  idempotencyKey?: string;
  signal?: AbortSignal;
};

export async function postJson<T>(
  path: string,
  body: Record<string, unknown>,
  options?: PipelinePostOptions,
): Promise<T> {
  const headers: Record<string, string> = {
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
  return readJson<T>(response);
}
