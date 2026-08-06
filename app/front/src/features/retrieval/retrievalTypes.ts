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

export type RetrievalStage = "unavailable" | "loading" | "ready" | "blocked";

export type RetrievalStageState = {
  stage: RetrievalStage;
  blockingReasons: string[];
};
