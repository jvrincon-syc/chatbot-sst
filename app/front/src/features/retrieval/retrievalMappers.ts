import type {
  RetrievalEvidence,
  RetrievalProfile,
  RetrievalProfileStatus,
  RetrievalReadiness,
  RetrievalSearchResult,
  RetrievalRuntimeStatus,
  RetrievalValidationResult,
} from "./retrievalTypes.js";

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function toNullableString(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function toNullableNumber(value: unknown): number | null {
  return value === null || value === undefined ? null : Number(value);
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function toRetrievalProfile(payload: Record<string, unknown>): RetrievalProfile {
  return {
    retrievalProfileId: String(payload.retrieval_profile_id ?? ""),
    consumerScopeType: String(payload.consumer_scope_type ?? ""),
    consumerScopeId: String(payload.consumer_scope_id ?? ""),
    corpusVersion: String(payload.corpus_version ?? ""),
    embeddingProfileId: String(payload.embedding_profile_id ?? ""),
    indexingTargetId: String(payload.indexing_target_id ?? ""),
    lexicalFallbackPolicy: String(payload.lexical_fallback_policy ?? ""),
    active: Boolean(payload.active),
    validationStatus: String(payload.validation_status ?? ""),
    validatedAt: toNullableString(payload.validated_at),
    lastRuntimeStatus: String(payload.last_runtime_status ?? ""),
    createdAt: toNullableString(payload.created_at),
    deprecatedAt: toNullableString(payload.deprecated_at),
  };
}

export function toRetrievalRuntimeStatus(
  payload: Record<string, unknown>,
): RetrievalRuntimeStatus {
  return {
    retrievalProfileId: String(payload.retrieval_profile_id ?? ""),
    embeddingProfileId: String(payload.embedding_profile_id ?? ""),
    indexingTargetId: String(payload.indexing_target_id ?? ""),
    queryEngineAvailable: Boolean(payload.query_engine_available),
    engineRevisionObserved: String(payload.engine_revision_observed ?? ""),
    vectorRetrievalEnabled: Boolean(payload.vector_retrieval_enabled),
    lexicalFallbackAllowed: Boolean(payload.lexical_fallback_allowed),
    blockedReason: toNullableString(payload.blocked_reason),
  };
}

export function toRetrievalReadiness(payload: Record<string, unknown>): RetrievalReadiness {
  return {
    retrievalProfileId: String(payload.retrieval_profile_id ?? ""),
    ready: Boolean(payload.ready),
    activeVectorRows: Number(payload.active_vector_rows ?? 0),
    activeDocumentCount: Number(payload.active_document_count ?? 0),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
    blockingReasons: toStringArray(payload.blocking_reasons),
  };
}

export function toRetrievalProfileStatus(
  payload: Record<string, unknown>,
): RetrievalProfileStatus {
  return {
    profile: toRetrievalProfile(toRecord(payload.profile)),
    runtime: toRetrievalRuntimeStatus(toRecord(payload.runtime)),
    readiness: toRetrievalReadiness(toRecord(payload.readiness)),
  };
}

export function toRetrievalValidationResult(
  payload: Record<string, unknown>,
): RetrievalValidationResult {
  return {
    retrievalProfileId: String(payload.retrieval_profile_id ?? ""),
    status: String(payload.status ?? ""),
    validatorVersion: String(payload.validator_version ?? ""),
    queryDimension: toNullableNumber(payload.query_dimension),
    candidatesFound: Number(payload.candidates_found ?? 0),
    blockingReasons: toStringArray(payload.blocking_reasons),
  };
}

export function toRetrievalEvidence(payload: Record<string, unknown>): RetrievalEvidence {
  return {
    nodeId: String(payload.node_id ?? ""),
    documentId: String(payload.document_id ?? ""),
    parentNodeId: toNullableString(payload.parent_node_id),
    childChunkId: String(payload.child_chunk_id ?? ""),
    text: String(payload.text ?? ""),
    score: Number(payload.score ?? 0),
    source: String(payload.source ?? ""),
    pageStart: toNullableNumber(payload.page_start),
    pageEnd: toNullableNumber(payload.page_end),
    sectionTitle: toNullableString(payload.section_title),
    sectionPath: toNullableString(payload.section_path),
    metadata: toRecord(payload.metadata),
    embeddingProfileId: String(payload.embedding_profile_id ?? ""),
    corpusVersion: String(payload.corpus_version ?? ""),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
  };
}

export function toRetrievalSearchResult(
  payload: Record<string, unknown>,
): RetrievalSearchResult {
  return {
    retrievalProfileId: String(payload.retrieval_profile_id ?? ""),
    topK: Number(payload.top_k ?? 0),
    items: Array.isArray(payload.items)
      ? payload.items
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map(toRetrievalEvidence)
      : [],
  };
}
