import type {
  ChunkingChildrenPage,
  ChunkingErrorEnvelope,
  ChunkingParentsPage,
  ChunkingProfile,
  ChunkingRunDocument,
  ChunkingRunDocumentsPage,
  ChunkingRunRequest,
  ChunkingRunSummary,
  ChunkingStoredDocument,
  ChunkingStoredDocumentsPage,
  ChunkingValidation,
} from "./chunkingTypes.js";
import { readJsonResponse } from "../../shared/readJsonResponse.js";

type ChunkingHttpError = Error & {
  status: number;
  code: string | null;
  runId: string | null;
  details: Record<string, unknown>;
};

function toChunkingErrorEnvelope(payload: unknown): ChunkingErrorEnvelope {
  return payload && typeof payload === "object" ? (payload as ChunkingErrorEnvelope) : {};
}

function toChunkingHttpError(response: Response, payload: unknown): ChunkingHttpError {
  const envelope = toChunkingErrorEnvelope(payload);
  const error = new Error(envelope.error?.message ?? `HTTP ${response.status}`) as ChunkingHttpError;
  error.status = response.status;
  error.code = envelope.error?.code ?? null;
  error.runId = envelope.error?.run_id ?? null;
  error.details = envelope.error?.details ?? {};
  return error;
}

function isChunkingHttpError(error: unknown): error is ChunkingHttpError {
  return error instanceof Error && typeof (error as ChunkingHttpError).status === "number";
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await readJsonResponse<unknown>(response);
  if (!response.ok) {
    throw toChunkingHttpError(response, payload);
  }
  return payload as T;
}

function toProfile(payload: Record<string, unknown>): ChunkingProfile {
  return {
    profileId: String(payload.profile_id ?? ""),
    childMinTokens: Number(payload.child_min_tokens ?? 0),
    childTargetTokens: Number(payload.child_target_tokens ?? 0),
    childMaxTokens: Number(payload.child_max_tokens ?? 0),
    overlapRatio: Number(payload.overlap_ratio ?? 0),
    overlapMinTokens: Number(payload.overlap_min_tokens ?? 0),
    overlapMaxTokens: Number(payload.overlap_max_tokens ?? 0),
  };
}

function toRunSummary(payload: Record<string, unknown>): ChunkingRunSummary {
  return {
    runId: String(payload.run_id ?? ""),
    status: String(payload.status ?? ""),
    profileId: String(payload.profile_id ?? ""),
    requestedDocuments: Number(payload.requested_documents ?? 0),
    completedDocuments: Number(payload.completed_documents ?? 0),
    warnings: Array.isArray(payload.warnings) ? payload.warnings.map((item) => String(item)) : [],
    links: {
      self: String((payload.links as Record<string, unknown> | undefined)?.self ?? ""),
      documents: String((payload.links as Record<string, unknown> | undefined)?.documents ?? ""),
      validation: String((payload.links as Record<string, unknown> | undefined)?.validation ?? ""),
    },
  };
}

function toRunDocument(payload: Record<string, unknown>): ChunkingRunDocument {
  return {
    documentId: String(payload.document_id ?? ""),
    status: String(payload.status ?? ""),
    reused: Boolean(payload.reused),
    runId: String(payload.run_id ?? ""),
    normalizedRelpath: String(payload.normalized_relpath ?? ""),
  };
}

function toStoredDocument(payload: Record<string, unknown>): ChunkingStoredDocument {
  return {
    documentId: String(payload.document_id ?? ""),
    normalizedRelpath: String(payload.normalized_relpath ?? ""),
    sourceRelpath: String(payload.source_relpath ?? ""),
    profileId: String(payload.profile_id ?? ""),
    parentCount: Number(payload.parent_count ?? 0),
    childCount: Number(payload.child_count ?? 0),
  };
}

function toRunDocumentsPage(payload: Record<string, unknown>): ChunkingRunDocumentsPage {
  return {
    items: Array.isArray(payload.items)
      ? payload.items
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map(toRunDocument)
      : [],
    page: Number(payload.page ?? 1),
    pageSize: Number(payload.page_size ?? 25),
    totalItems: Number(payload.total_items ?? 0),
    totalPages: Number(payload.total_pages ?? 0),
  };
}

function toStoredDocumentsPage(payload: Record<string, unknown>): ChunkingStoredDocumentsPage {
  return {
    items: Array.isArray(payload.items)
      ? payload.items
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map(toStoredDocument)
      : [],
    page: Number(payload.page ?? 1),
    pageSize: Number(payload.page_size ?? 25),
    totalItems: Number(payload.total_items ?? 0),
    totalPages: Number(payload.total_pages ?? 0),
  };
}

function toPaginationChunk<T>(
  payload: Record<string, unknown>,
  mapper: (item: Record<string, unknown>) => T,
): { items: T[]; page: number; pageSize: number; totalItems: number; totalPages: number } {
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

function toSourceSpan(payload: Record<string, unknown>) {
  return {
    pageStart: payload.page_start === null ? null : Number(payload.page_start ?? 0),
    pageEnd: payload.page_end === null ? null : Number(payload.page_end ?? 0),
    charStart: Number(payload.char_start ?? 0),
    charEnd: Number(payload.char_end ?? 0),
  };
}

function toParent(payload: Record<string, unknown>) {
  return {
    chunkId: String(payload.chunk_id ?? ""),
    documentId: String(payload.document_id ?? ""),
    profileId: String(payload.profile_id ?? ""),
    ordinal: Number(payload.ordinal ?? 0),
    text: String(payload.text ?? ""),
    sourceSpan: toSourceSpan((payload.source_span as Record<string, unknown>) ?? {}),
    blockIds: Array.isArray(payload.block_ids) ? payload.block_ids.map((item) => String(item)) : [],
  };
}

function toChild(payload: Record<string, unknown>) {
  const overlapPreviousSpan = payload.overlap_previous_span;
  const overlapNextSpan = payload.overlap_next_span;
  return {
    chunkId: String(payload.chunk_id ?? ""),
    documentId: String(payload.document_id ?? ""),
    profileId: String(payload.profile_id ?? ""),
    parentId: String(payload.parent_id ?? ""),
    ordinal: Number(payload.ordinal ?? 0),
    contextPrefix: String(payload.context_prefix ?? ""),
    text: String(payload.text ?? ""),
    sourceSpan: toSourceSpan((payload.source_span as Record<string, unknown>) ?? {}),
    tokenStart: Number(payload.token_start ?? 0),
    tokenEnd: Number(payload.token_end ?? 0),
    tokenCount: Number(payload.token_count ?? 0),
    overlapPreviousTokens: Number(payload.overlap_previous_tokens ?? 0),
    overlapNextTokens: Number(payload.overlap_next_tokens ?? 0),
    overlapPreviousSpan:
      overlapPreviousSpan && typeof overlapPreviousSpan === "object"
        ? {
            tokenStart: Number((overlapPreviousSpan as Record<string, unknown>).token_start ?? 0),
            tokenEnd: Number((overlapPreviousSpan as Record<string, unknown>).token_end ?? 0),
          }
        : null,
    overlapNextSpan:
      overlapNextSpan && typeof overlapNextSpan === "object"
        ? {
            tokenStart: Number((overlapNextSpan as Record<string, unknown>).token_start ?? 0),
            tokenEnd: Number((overlapNextSpan as Record<string, unknown>).token_end ?? 0),
          }
        : null,
    zeroOverlapReasons: Array.isArray(payload.zero_overlap_reasons)
      ? payload.zero_overlap_reasons.map((item) => String(item))
      : [],
    warnings: Array.isArray(payload.warnings) ? payload.warnings.map((item) => String(item)) : [],
  };
}

function toValidation(payload: Record<string, unknown>): ChunkingValidation {
  return {
    runId: String(payload.run_id ?? ""),
    status: String(payload.status ?? ""),
    documentsChecked: Number(payload.documents_checked ?? 0),
    errors: Number(payload.errors ?? 0),
    warnings: Number(payload.warnings ?? 0),
    checks: Array.isArray(payload.checks)
      ? payload.checks.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
      : [],
  };
}

export async function loadChunkingProfiles(): Promise<ChunkingProfile[]> {
  const response = await fetch("/api/chunking/profiles");
  const payload = await readJson<unknown[]>(response);
  return payload
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map(toProfile);
}

export async function createChunkingRun(options: {
  request: ChunkingRunRequest;
  idempotencyKey: string;
}): Promise<ChunkingRunSummary> {
  const response = await fetch("/api/chunking/runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": options.idempotencyKey,
    },
    body: JSON.stringify({
      scope: options.request.scope,
      document_ids: options.request.documentIds,
      profile_id: options.request.profileId,
      force: options.request.force,
    }),
  });
  return toRunSummary((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>);
}

export async function loadChunkingRun(runId: string): Promise<ChunkingRunSummary> {
  const response = await fetch(`/api/chunking/runs/${encodeURIComponent(runId)}`);
  return toRunSummary((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>);
}

export async function loadChunkingRunDocuments(options: {
  runId: string;
  page?: number;
  pageSize?: number;
}): Promise<ChunkingRunDocumentsPage> {
  const params = new URLSearchParams();
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `/api/chunking/runs/${encodeURIComponent(options.runId)}/documents${suffix}`,
  );
  return toRunDocumentsPage((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>);
}

export async function loadChunkingStoredDocuments(options?: {
  page?: number;
  pageSize?: number;
}): Promise<ChunkingStoredDocumentsPage> {
  const params = new URLSearchParams();
  if (options?.page) params.set("page", String(options.page));
  if (options?.pageSize) params.set("page_size", String(options.pageSize));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`/api/chunking/documents${suffix}`);
  return toStoredDocumentsPage((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>);
}

export async function loadChunkingValidation(runId: string): Promise<ChunkingValidation> {
  const response = await fetch(`/api/chunking/runs/${encodeURIComponent(runId)}/validation`);
  return toValidation((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>);
}

export async function loadChunkingValidationOptional(runId: string): Promise<ChunkingValidation | null> {
  try {
    return await loadChunkingValidation(runId);
  } catch (error) {
    if (isChunkingHttpError(error) && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function loadChunkingParents(options: {
  documentId: string;
  runId?: string | null;
  page?: number;
  pageSize?: number;
}): Promise<ChunkingParentsPage> {
  const params = new URLSearchParams();
  if (options.runId) params.set("run_id", options.runId);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `/api/chunking/documents/${encodeURIComponent(options.documentId)}/parents${suffix}`,
  );
  return toPaginationChunk((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>, toParent);
}

export async function loadChunkingChildren(options: {
  parentId: string;
  page?: number;
  pageSize?: number;
}): Promise<ChunkingChildrenPage> {
  const params = new URLSearchParams();
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `/api/chunking/parents/${encodeURIComponent(options.parentId)}/children${suffix}`,
  );
  return toPaginationChunk((await readJson<Record<string, unknown>>(response)) as Record<string, unknown>, toChild);
}
