import type {
  EmbeddingBundleChunk,
  EmbeddingBundleSummary,
  EmbeddingBundleValidation,
  EmbeddingBundleValidationCheck,
  EmbeddingChunkBundleListItem,
  EmbeddingChunkBundleSummary,
  EmbeddingIndexingReadiness,
  EmbeddingProfile,
  EmbeddingRun,
  EmbeddingRuntimeStatus,
} from "./embeddingTypes.js";

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function toNullableString(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function toEmbeddingProfile(payload: Record<string, unknown>): EmbeddingProfile {
  return {
    profileId: String(payload.profile_id ?? ""),
    provider: String(payload.provider ?? ""),
    model: String(payload.model ?? ""),
    modelRevision: String(payload.model_revision ?? ""),
    dimension: Number(payload.dimension ?? 0),
    normalization: String(payload.normalization ?? ""),
    distanceMetric: String(payload.distance_metric ?? ""),
    configurationFingerprint: toNullableString(payload.configuration_fingerprint),
    ingestionOrigin: String(payload.ingestion_origin ?? ""),
    chunkingVersion: String(payload.chunking_version ?? ""),
    vectorTable: String(payload.vector_table ?? ""),
    defaultIndexingTargetId: toNullableString(payload.default_indexing_target_id),
    active: Boolean(payload.active),
    documentEnabled: Boolean(payload.document_enabled),
    queryEnabled: Boolean(payload.query_enabled),
    compatibilityStatus: String(payload.compatibility_status ?? ""),
    deprecatedAt: toNullableString(payload.deprecated_at),
    canEmbedDocuments: Boolean(payload.can_embed_documents),
    canEmbedQueries: Boolean(payload.can_embed_queries),
  };
}

export function toEmbeddingRuntimeStatus(payload: Record<string, unknown>): EmbeddingRuntimeStatus {
  return {
    profileId: String(payload.profile_id ?? ""),
    provider: String(payload.provider ?? ""),
    model: String(payload.model ?? ""),
    runtimeMode: String(payload.runtime_mode ?? ""),
    engineAvailable: Boolean(payload.engine_available),
    engineRevisionObserved: String(payload.engine_revision_observed ?? ""),
    supportsDocuments: Boolean(payload.supports_documents),
    supportsQueries: Boolean(payload.supports_queries),
    blockedReason: toNullableString(payload.blocked_reason),
  };
}

export function toEmbeddingChunkBundleListItem(
  payload: Record<string, unknown>,
): EmbeddingChunkBundleListItem {
  return {
    chunkBundleId: String(payload.chunk_bundle_id ?? ""),
    bundleFingerprint: String(payload.bundle_fingerprint ?? ""),
    profileId: String(payload.profile_id ?? ""),
    corpusVersion: String(payload.corpus_version ?? ""),
    sourceDocumentId: String(payload.source_document_id ?? ""),
    parentCount: Number(payload.parent_count ?? 0),
    childCount: Number(payload.child_count ?? 0),
    status: String(payload.status ?? ""),
  };
}

export function toEmbeddingChunkBundleSummary(
  payload: Record<string, unknown>,
): EmbeddingChunkBundleSummary {
  return {
    ...toEmbeddingChunkBundleListItem(payload),
    profileFingerprint: toNullableString(payload.profile_fingerprint),
    embeddingBundleIds: toStringArray(payload.embedding_bundle_ids),
  };
}

export function toEmbeddingRun(payload: Record<string, unknown>): EmbeddingRun {
  const summary = toRecord(payload.summary);
  const links = toRecord(payload.links);
  return {
    embeddingRunId: String(payload.embedding_run_id ?? ""),
    idempotencyKey: String(payload.idempotency_key ?? ""),
    requestFingerprint: String(payload.request_fingerprint ?? ""),
    sourceChunkBundleId: String(payload.source_chunk_bundle_id ?? ""),
    embeddingProfileId: String(payload.embedding_profile_id ?? ""),
    configurationFingerprint: toNullableString(payload.configuration_fingerprint),
    runtimeEngine: String(payload.runtime_engine ?? ""),
    runtimeMode: String(payload.runtime_mode ?? ""),
    engineRevisionObserved: String(payload.engine_revision_observed ?? ""),
    status: String(payload.status ?? ""),
    startedAt: toNullableString(payload.started_at),
    completedAt: toNullableString(payload.completed_at),
    createdAt: toNullableString(payload.created_at),
    summary: {
      requestedChildren: Number(summary.requested_children ?? 0),
      embeddedChildren: Number(summary.embedded_children ?? 0),
      documentId: toNullableString(summary.document_id),
    },
    warnings: toStringArray(payload.warnings),
    errorSummary: toNullableString(payload.error_summary),
    producedEmbeddingBundleId: toNullableString(payload.produced_embedding_bundle_id),
    links: {
      self: String(links.self ?? ""),
    },
  };
}

export function toEmbeddingBundleSummary(payload: Record<string, unknown>): EmbeddingBundleSummary {
  const checksums = toRecord(payload.checksums);
  const links = toRecord(payload.links);
  const mappedChecksums: Record<string, string> = {};
  for (const [key, value] of Object.entries(checksums)) {
    mappedChecksums[key] = String(value);
  }
  return {
    embeddingBundleId: String(payload.embedding_bundle_id ?? ""),
    sourceChunkBundleId: String(payload.source_chunk_bundle_id ?? ""),
    embeddingProfileId: String(payload.embedding_profile_id ?? ""),
    provider: String(payload.provider ?? ""),
    model: String(payload.model ?? ""),
    modelRevision: String(payload.model_revision ?? ""),
    dimension: Number(payload.dimension ?? 0),
    normalization: String(payload.normalization ?? ""),
    distanceMetric: String(payload.distance_metric ?? ""),
    configurationFingerprint: toNullableString(payload.configuration_fingerprint),
    corpusVersion: String(payload.corpus_version ?? ""),
    bundleSchemaVersion: String(payload.bundle_schema_version ?? ""),
    sourceContentFingerprint: toNullableString(payload.source_content_fingerprint),
    vectorDtype: String(payload.vector_dtype ?? ""),
    vectorShape: String(payload.vector_shape ?? ""),
    vectorCount: Number(payload.vector_count ?? 0),
    checksums: mappedChecksums,
    status: String(payload.status ?? ""),
    validationStatus: String(payload.validation_status ?? ""),
    readinessStatus: String(payload.readiness_status ?? ""),
    sealedAt: toNullableString(payload.sealed_at),
    links: {
      self: String(links.self ?? ""),
      chunks: String(links.chunks ?? ""),
      validation: String(links.validation ?? ""),
      indexingReadiness: String(links.indexing_readiness ?? ""),
    },
  };
}

export function toEmbeddingBundleChunk(payload: Record<string, unknown>): EmbeddingBundleChunk {
  return {
    childChunkId: String(payload.child_chunk_id ?? ""),
    parentChunkId: String(payload.parent_chunk_id ?? ""),
    documentId: String(payload.document_id ?? ""),
    vectorOffset: Number(payload.vector_offset ?? 0),
    vectorLength: Number(payload.vector_length ?? 0),
    vectorChecksum: String(payload.vector_checksum ?? ""),
    contentHash: String(payload.content_hash ?? ""),
    chunkOrdinal: Number(payload.chunk_ordinal ?? 0),
  };
}

export function toEmbeddingBundleValidation(
  payload: Record<string, unknown>,
): EmbeddingBundleValidation {
  return {
    embeddingBundleId: String(payload.embedding_bundle_id ?? ""),
    status: String(payload.status ?? ""),
    validatorVersion: String(payload.validator_version ?? ""),
    checks: Array.isArray(payload.checks)
      ? payload.checks
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
          .map(toEmbeddingBundleValidationCheck)
      : [],
  };
}

function toEmbeddingBundleValidationCheck(
  payload: Record<string, unknown>,
): EmbeddingBundleValidationCheck {
  return {
    name: String(payload.name ?? ""),
    passed: Boolean(payload.passed),
    detail: String(payload.detail ?? ""),
  };
}

export function toEmbeddingIndexingReadiness(
  payload: Record<string, unknown>,
): EmbeddingIndexingReadiness {
  return {
    embeddingBundleId: String(payload.embedding_bundle_id ?? ""),
    indexingTargetId: toNullableString(payload.indexing_target_id),
    status: String(payload.status ?? ""),
    blockingReasons: toStringArray(payload.blocking_reasons),
  };
}
