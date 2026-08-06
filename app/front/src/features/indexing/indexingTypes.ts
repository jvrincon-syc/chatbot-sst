export type IndexingOverview = {
  targets: number;
  activeTargets: number;
  profiles: number;
  verifiedProfiles: number;
  sealedBundles: number;
  runs: number;
  completedRuns: number;
  activeRuns: number;
  bundleFirstEnabled: boolean;
};

export type IndexingTarget = {
  indexingTargetId: string;
  postgresSchema: string;
  vectorTable: string;
  distanceOps: string;
  storageSchemaVersion: string;
  active: boolean;
  deprecatedAt: string | null;
};

export type IndexingRunRequest = {
  embeddingBundleId: string;
};

export type IndexingRunSummaryMetrics = {
  requestedDocuments: number;
  committedDocuments: number;
  interrupted: boolean;
};

export type IndexingRunLinks = {
  self: string;
  documents: string;
  errors: string;
  retrievalReadiness: string;
};

export type IndexingRun = {
  runId: string;
  profileId: string;
  status: string;
  embeddingBundleId: string | null;
  embeddingProfileId: string | null;
  indexingTargetId: string | null;
  corpusVersion: string;
  idempotencyKey: string;
  requestFingerprint: string;
  validationStatus: string;
  activationStatus: string;
  startedAt: string | null;
  completedAt: string | null;
  summary: IndexingRunSummaryMetrics;
  warnings: string[];
  links: IndexingRunLinks;
};

export type IndexingRunDocument = {
  documentId: string;
  sourceRelpath: string;
  status: string;
  eligibilityStatus: string;
  eligibilityReason: string;
  sourceChunkBundleId: string | null;
  embeddingBundleId: string | null;
  parentCount: number;
  childCount: number;
  vectorCount: number;
  startedAt: string | null;
  committedAt: string | null;
  errorCode: string | null;
  internalErrorId: string | null;
};

export type IndexingRunError = {
  documentId: string;
  status: string;
  errorCode: string | null;
  internalErrorId: string | null;
};

export type IndexingRetrievalReadiness = {
  runId: string;
  embeddingBundleId: string | null;
  indexingTargetId: string | null;
  corpusVersion: string;
  ready: boolean;
  activeVectorRows: number;
  blockingReasons: string[];
};

export type ActivationRequest = {
  runId: string;
  lexicalFallbackPolicy: string;
};

export type ActivationResult = {
  runId: string;
  embeddingBundleId: string | null;
  indexingTargetId: string | null;
  retrievalProfileId: string | null;
  activatedRows: number;
};
