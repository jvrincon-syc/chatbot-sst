import { readJsonResponse } from "../../shared/readJsonResponse.js";
function toChunkingErrorEnvelope(payload) {
    return payload && typeof payload === "object" ? payload : {};
}
function toChunkingHttpError(response, payload) {
    const envelope = toChunkingErrorEnvelope(payload);
    const error = new Error(envelope.error?.message ?? `HTTP ${response.status}`);
    error.status = response.status;
    error.code = envelope.error?.code ?? null;
    error.runId = envelope.error?.run_id ?? null;
    error.details = envelope.error?.details ?? {};
    return error;
}
function isChunkingHttpError(error) {
    return error instanceof Error && typeof error.status === "number";
}
async function readJson(response) {
    const payload = await readJsonResponse(response);
    if (!response.ok) {
        throw toChunkingHttpError(response, payload);
    }
    return payload;
}
function toProfile(payload) {
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
function toRunSummary(payload) {
    return {
        runId: String(payload.run_id ?? ""),
        status: String(payload.status ?? ""),
        profileId: String(payload.profile_id ?? ""),
        requestedDocuments: Number(payload.requested_documents ?? 0),
        completedDocuments: Number(payload.completed_documents ?? 0),
        warnings: Array.isArray(payload.warnings) ? payload.warnings.map((item) => String(item)) : [],
        links: {
            self: String(payload.links?.self ?? ""),
            documents: String(payload.links?.documents ?? ""),
            validation: String(payload.links?.validation ?? ""),
        },
    };
}
function toRunDocument(payload) {
    return {
        documentId: String(payload.document_id ?? ""),
        status: String(payload.status ?? ""),
        reused: Boolean(payload.reused),
        runId: String(payload.run_id ?? ""),
        normalizedRelpath: String(payload.normalized_relpath ?? ""),
    };
}
function toStoredDocument(payload) {
    return {
        documentId: String(payload.document_id ?? ""),
        normalizedRelpath: String(payload.normalized_relpath ?? ""),
        sourceRelpath: String(payload.source_relpath ?? ""),
        profileId: String(payload.profile_id ?? ""),
        parentCount: Number(payload.parent_count ?? 0),
        childCount: Number(payload.child_count ?? 0),
    };
}
function toRunDocumentsPage(payload) {
    return {
        items: Array.isArray(payload.items)
            ? payload.items
                .filter((item) => typeof item === "object" && item !== null)
                .map(toRunDocument)
            : [],
        page: Number(payload.page ?? 1),
        pageSize: Number(payload.page_size ?? 25),
        totalItems: Number(payload.total_items ?? 0),
        totalPages: Number(payload.total_pages ?? 0),
    };
}
function toStoredDocumentsPage(payload) {
    return {
        items: Array.isArray(payload.items)
            ? payload.items
                .filter((item) => typeof item === "object" && item !== null)
                .map(toStoredDocument)
            : [],
        page: Number(payload.page ?? 1),
        pageSize: Number(payload.page_size ?? 25),
        totalItems: Number(payload.total_items ?? 0),
        totalPages: Number(payload.total_pages ?? 0),
    };
}
function toPaginationChunk(payload, mapper) {
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
function toSourceSpan(payload) {
    return {
        pageStart: payload.page_start === null ? null : Number(payload.page_start ?? 0),
        pageEnd: payload.page_end === null ? null : Number(payload.page_end ?? 0),
        charStart: Number(payload.char_start ?? 0),
        charEnd: Number(payload.char_end ?? 0),
    };
}
function toParent(payload) {
    return {
        chunkId: String(payload.chunk_id ?? ""),
        documentId: String(payload.document_id ?? ""),
        profileId: String(payload.profile_id ?? ""),
        ordinal: Number(payload.ordinal ?? 0),
        text: String(payload.text ?? ""),
        sourceSpan: toSourceSpan(payload.source_span ?? {}),
        blockIds: Array.isArray(payload.block_ids) ? payload.block_ids.map((item) => String(item)) : [],
    };
}
function toChild(payload) {
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
        sourceSpan: toSourceSpan(payload.source_span ?? {}),
        tokenStart: Number(payload.token_start ?? 0),
        tokenEnd: Number(payload.token_end ?? 0),
        tokenCount: Number(payload.token_count ?? 0),
        overlapPreviousTokens: Number(payload.overlap_previous_tokens ?? 0),
        overlapNextTokens: Number(payload.overlap_next_tokens ?? 0),
        overlapPreviousSpan: overlapPreviousSpan && typeof overlapPreviousSpan === "object"
            ? {
                tokenStart: Number(overlapPreviousSpan.token_start ?? 0),
                tokenEnd: Number(overlapPreviousSpan.token_end ?? 0),
            }
            : null,
        overlapNextSpan: overlapNextSpan && typeof overlapNextSpan === "object"
            ? {
                tokenStart: Number(overlapNextSpan.token_start ?? 0),
                tokenEnd: Number(overlapNextSpan.token_end ?? 0),
            }
            : null,
        zeroOverlapReasons: Array.isArray(payload.zero_overlap_reasons)
            ? payload.zero_overlap_reasons.map((item) => String(item))
            : [],
        warnings: Array.isArray(payload.warnings) ? payload.warnings.map((item) => String(item)) : [],
    };
}
function toValidation(payload) {
    return {
        runId: String(payload.run_id ?? ""),
        status: String(payload.status ?? ""),
        documentsChecked: Number(payload.documents_checked ?? 0),
        errors: Number(payload.errors ?? 0),
        warnings: Number(payload.warnings ?? 0),
        checks: Array.isArray(payload.checks)
            ? payload.checks.filter((item) => typeof item === "object" && item !== null)
            : [],
    };
}
export async function loadChunkingProfiles() {
    const response = await fetch("/api/chunking/profiles");
    const payload = await readJson(response);
    return payload
        .filter((item) => typeof item === "object" && item !== null)
        .map(toProfile);
}
export async function createChunkingRun(options) {
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
    return toRunSummary((await readJson(response)));
}
export async function loadChunkingRun(runId) {
    const response = await fetch(`/api/chunking/runs/${encodeURIComponent(runId)}`);
    return toRunSummary((await readJson(response)));
}
export async function loadChunkingRunDocuments(options) {
    const params = new URLSearchParams();
    if (options.page)
        params.set("page", String(options.page));
    if (options.pageSize)
        params.set("page_size", String(options.pageSize));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`/api/chunking/runs/${encodeURIComponent(options.runId)}/documents${suffix}`);
    return toRunDocumentsPage((await readJson(response)));
}
export async function loadChunkingStoredDocuments(options) {
    const params = new URLSearchParams();
    if (options?.page)
        params.set("page", String(options.page));
    if (options?.pageSize)
        params.set("page_size", String(options.pageSize));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`/api/chunking/documents${suffix}`);
    return toStoredDocumentsPage((await readJson(response)));
}
export async function loadChunkingValidation(runId) {
    const response = await fetch(`/api/chunking/runs/${encodeURIComponent(runId)}/validation`);
    return toValidation((await readJson(response)));
}
export async function loadChunkingValidationOptional(runId) {
    try {
        return await loadChunkingValidation(runId);
    }
    catch (error) {
        if (isChunkingHttpError(error) && error.status === 404) {
            return null;
        }
        throw error;
    }
}
export async function loadChunkingParents(options) {
    const params = new URLSearchParams();
    if (options.runId)
        params.set("run_id", options.runId);
    if (options.page)
        params.set("page", String(options.page));
    if (options.pageSize)
        params.set("page_size", String(options.pageSize));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`/api/chunking/documents/${encodeURIComponent(options.documentId)}/parents${suffix}`);
    return toPaginationChunk((await readJson(response)), toParent);
}
export async function loadChunkingChildren(options) {
    const params = new URLSearchParams();
    if (options.page)
        params.set("page", String(options.page));
    if (options.pageSize)
        params.set("page_size", String(options.pageSize));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`/api/chunking/parents/${encodeURIComponent(options.parentId)}/children${suffix}`);
    return toPaginationChunk((await readJson(response)), toChild);
}
