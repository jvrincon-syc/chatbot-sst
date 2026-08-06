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

export const DEFAULT_LEXICAL_FALLBACK_POLICY = "allowed_when_vector_unavailable";

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function toNullableString(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

// Indexing runs consume a single embedding bundle. The frontend never chooses
// target/provider/dimension/consumer scope; the body carries only the bundle id.
export function toIndexingRunRequest(embeddingBundleId: string): { embedding_bundle_id: string } {
  return { embedding_bundle_id: embeddingBundleId };
}

// Activation is a separate operator action. The consumer scope is resolved
// server-side and must never be sent in the body.
export function toActivationRequest(
  runId: string,
  lexicalFallbackPolicy: string = DEFAULT_LEXICAL_FALLBACK_POLICY,
): { run_id: string; lexical_fallback_policy: string } {
  return { run_id: runId, lexical_fallback_policy: lexicalFallbackPolicy };
}

export function indexingRunRequestFrom(request: IndexingRunRequest): { embedding_bundle_id: string } {
  return toIndexingRunRequest(request.embeddingBundleId);
}

export function activationRequestFrom(request: ActivationRequest): {
  run_id: string;
  lexical_fallback_policy: string;
} {
  return toActivationRequest(request.runId, request.lexicalFallbackPolicy);
}

export function toIndexingOverview(payload: Record<string, unknown>): IndexingOverview {
  return {
    targets: Number(payload.targets ?? 0),
    activeTargets: Number(payload.active_targets ?? 0),
    profiles: Number(payload.profiles ?? 0),
    verifiedProfiles: Number(payload.verified_profiles ?? 0),
    sealedBundles: Number(payload.sealed_bundles ?? 0),
    runs: Number(payload.runs ?? 0),
    completedRuns: Number(payload.completed_runs ?? 0),
    activeRuns: Number(payload.active_runs ?? 0),
    bundleFirstEnabled: Boolean(payload.bundle_first_enabled),
  };
}

export function toIndexingTarget(payload: Record<string, unknown>): IndexingTarget {
  return {
    indexingTargetId: String(payload.indexing_target_id ?? ""),
    postgresSchema: String(payload.postgres_schema ?? ""),
    vectorTable: String(payload.vector_table ?? ""),
    distanceOps: String(payload.distance_ops ?? ""),
    storageSchemaVersion: String(payload.storage_schema_version ?? ""),
    active: Boolean(payload.active),
    deprecatedAt: toNullableString(payload.deprecated_at),
  };
}

export function toIndexingRun(payload: Record<string, unknown>): IndexingRun {
  const summary = toRecord(payload.summary);
  const links = toRecord(payload.links);
  return {
    runId: String(payload.run_id ?? ""),
    profileId: String(payload.profile_id ?? ""),
    status: String(payload.status ?? ""),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
    embeddingProfileId: toNullableString(payload.embedding_profile_id),
    indexingTargetId: toNullableString(payload.indexing_target_id),
    corpusVersion: String(payload.corpus_version ?? ""),
    idempotencyKey: String(payload.idempotency_key ?? ""),
    requestFingerprint: String(payload.request_fingerprint ?? ""),
    validationStatus: String(payload.validation_status ?? ""),
    activationStatus: String(payload.activation_status ?? ""),
    startedAt: toNullableString(payload.started_at),
    completedAt: toNullableString(payload.completed_at),
    summary: {
      requestedDocuments: Number(summary.requested_documents ?? 0),
      committedDocuments: Number(summary.committed_documents ?? 0),
      interrupted: Boolean(summary.interrupted),
    },
    warnings: toStringArray(payload.warnings),
    links: {
      self: String(links.self ?? ""),
      documents: String(links.documents ?? ""),
      errors: String(links.errors ?? ""),
      retrievalReadiness: String(links.retrieval_readiness ?? ""),
    },
  };
}

export function toIndexingRunDocument(payload: Record<string, unknown>): IndexingRunDocument {
  return {
    documentId: String(payload.document_id ?? ""),
    sourceRelpath: String(payload.source_relpath ?? ""),
    status: String(payload.status ?? ""),
    eligibilityStatus: String(payload.eligibility_status ?? ""),
    eligibilityReason: String(payload.eligibility_reason ?? ""),
    sourceChunkBundleId: toNullableString(payload.source_chunk_bundle_id),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
    parentCount: Number(payload.parent_count ?? 0),
    childCount: Number(payload.child_count ?? 0),
    vectorCount: Number(payload.vector_count ?? 0),
    startedAt: toNullableString(payload.started_at),
    committedAt: toNullableString(payload.committed_at),
    errorCode: toNullableString(payload.error_code),
    internalErrorId: toNullableString(payload.internal_error_id),
  };
}

export function toIndexingRunError(payload: Record<string, unknown>): IndexingRunError {
  return {
    documentId: String(payload.document_id ?? ""),
    status: String(payload.status ?? ""),
    errorCode: toNullableString(payload.error_code),
    internalErrorId: toNullableString(payload.internal_error_id),
  };
}

export function toIndexingRetrievalReadiness(
  payload: Record<string, unknown>,
): IndexingRetrievalReadiness {
  return {
    runId: String(payload.run_id ?? ""),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
    indexingTargetId: toNullableString(payload.indexing_target_id),
    corpusVersion: String(payload.corpus_version ?? ""),
    ready: Boolean(payload.ready),
    activeVectorRows: Number(payload.active_vector_rows ?? 0),
    blockingReasons: toStringArray(payload.blocking_reasons),
  };
}

export function toActivationResult(payload: Record<string, unknown>): ActivationResult {
  return {
    runId: String(payload.run_id ?? ""),
    embeddingBundleId: toNullableString(payload.embedding_bundle_id),
    indexingTargetId: toNullableString(payload.indexing_target_id),
    retrievalProfileId: toNullableString(payload.retrieval_profile_id),
    activatedRows: Number(payload.activated_rows ?? 0),
  };
}
