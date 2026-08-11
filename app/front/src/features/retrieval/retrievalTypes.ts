export type RetrievalProfile = {
  retrievalProfileId: string;
  consumerScopeType: string;
  consumerScopeId: string;
  corpusVersion: string;
  embeddingProfileId: string;
  indexingTargetId: string;
  lexicalFallbackPolicy: string;
  active: boolean;
  validationStatus: string;
  validatedAt: string | null;
  lastRuntimeStatus: string;
  createdAt: string | null;
  deprecatedAt: string | null;
};

export type RetrievalRuntimeStatus = {
  retrievalProfileId: string;
  embeddingProfileId: string;
  indexingTargetId: string;
  queryEngineAvailable: boolean;
  engineRevisionObserved: string;
  vectorRetrievalEnabled: boolean;
  lexicalFallbackAllowed: boolean;
  blockedReason: string | null;
};

export type RetrievalReadiness = {
  retrievalProfileId: string;
  ready: boolean;
  activeVectorRows: number;
  activeDocumentCount: number;
  embeddingBundleId: string | null;
  blockingReasons: string[];
};

export type RetrievalProfileStatus = {
  profile: RetrievalProfile;
  runtime: RetrievalRuntimeStatus;
  readiness: RetrievalReadiness;
};

export type RetrievalValidationResult = {
  retrievalProfileId: string;
  status: string;
  validatorVersion: string;
  queryDimension: number | null;
  candidatesFound: number;
  blockingReasons: string[];
};

export type RetrievalEvidence = {
  nodeId: string;
  documentId: string;
  parentNodeId: string | null;
  childChunkId: string;
  text: string;
  score: number;
  source: string;
  pageStart: number | null;
  pageEnd: number | null;
  sectionTitle: string | null;
  sectionPath: string | null;
  metadata: Record<string, unknown>;
  embeddingProfileId: string;
  corpusVersion: string;
  embeddingBundleId: string | null;
};

export type RetrievalSearchResult = {
  retrievalProfileId: string;
  topK: number;
  items: RetrievalEvidence[];
};

export type RetrievalStage = "unavailable" | "loading" | "ready" | "blocked";

export type RetrievalStageState = {
  stage: RetrievalStage;
  blockingReasons: string[];
};
