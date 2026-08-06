export type EmbeddingProfile = {
  profileId: string;
  provider: string;
  model: string;
  modelRevision: string;
  dimension: number;
  normalization: string;
  distanceMetric: string;
  configurationFingerprint: string | null;
  ingestionOrigin: string;
  chunkingVersion: string;
  vectorTable: string;
  defaultIndexingTargetId: string | null;
  active: boolean;
  documentEnabled: boolean;
  queryEnabled: boolean;
  compatibilityStatus: string;
  deprecatedAt: string | null;
  canEmbedDocuments: boolean;
  canEmbedQueries: boolean;
};

export type EmbeddingRuntimeStatus = {
  profileId: string;
  provider: string;
  model: string;
  runtimeMode: string;
  engineAvailable: boolean;
  engineRevisionObserved: string;
  supportsDocuments: boolean;
  supportsQueries: boolean;
  blockedReason: string | null;
};

export type EmbeddingChunkBundleListItem = {
  chunkBundleId: string;
  bundleFingerprint: string;
  profileId: string;
  corpusVersion: string;
  sourceDocumentId: string;
  parentCount: number;
  childCount: number;
  status: string;
};

export type EmbeddingChunkBundleSummary = EmbeddingChunkBundleListItem & {
  profileFingerprint: string | null;
  embeddingBundleIds: string[];
};

export type EmbeddingRunRequest = {
  chunkBundleId: string;
  profileId: string;
};

export type EmbeddingRunLinks = {
  self: string;
};

export type EmbeddingRun = {
  embeddingRunId: string;
  idempotencyKey: string;
  requestFingerprint: string;
  sourceChunkBundleId: string;
  embeddingProfileId: string;
  configurationFingerprint: string | null;
  runtimeEngine: string;
  runtimeMode: string;
  engineRevisionObserved: string;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string | null;
  summary: EmbeddingRunSummaryMetrics;
  warnings: string[];
  errorSummary: string | null;
  producedEmbeddingBundleId: string | null;
  links: EmbeddingRunLinks;
};

export type EmbeddingRunSummaryMetrics = {
  requestedChildren: number;
  embeddedChildren: number;
  documentId: string | null;
};

export type EmbeddingBundleChecksums = Record<string, string>;

export type EmbeddingBundleLinks = {
  self: string;
  chunks: string;
  validation: string;
  indexingReadiness: string;
};

export type EmbeddingBundleSummary = {
  embeddingBundleId: string;
  sourceChunkBundleId: string;
  embeddingProfileId: string;
  provider: string;
  model: string;
  modelRevision: string;
  dimension: number;
  normalization: string;
  distanceMetric: string;
  configurationFingerprint: string | null;
  corpusVersion: string;
  bundleSchemaVersion: string;
  sourceContentFingerprint: string | null;
  vectorDtype: string;
  vectorShape: string;
  vectorCount: number;
  checksums: EmbeddingBundleChecksums;
  status: string;
  validationStatus: string;
  readinessStatus: string;
  sealedAt: string | null;
  links: EmbeddingBundleLinks;
};

export type EmbeddingBundleChunk = {
  childChunkId: string;
  parentChunkId: string;
  documentId: string;
  vectorOffset: number;
  vectorLength: number;
  vectorChecksum: string;
  contentHash: string;
  chunkOrdinal: number;
};

export type EmbeddingBundleValidationCheck = {
  name: string;
  passed: boolean;
  detail: string;
};

export type EmbeddingBundleValidation = {
  embeddingBundleId: string;
  status: string;
  validatorVersion: string;
  checks: EmbeddingBundleValidationCheck[];
};

export type EmbeddingIndexingReadiness = {
  embeddingBundleId: string;
  indexingTargetId: string | null;
  status: string;
  blockingReasons: string[];
};
