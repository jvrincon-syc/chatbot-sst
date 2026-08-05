export type ChunkingScope = "documents" | "corpus";

export type ChunkingProfile = {
  profileId: string;
  childMinTokens: number;
  childTargetTokens: number;
  childMaxTokens: number;
  overlapRatio: number;
  overlapMinTokens: number;
  overlapMaxTokens: number;
};

export type ChunkingRunRequest = {
  scope: ChunkingScope;
  documentIds: string[];
  profileId: string;
  force: boolean;
};

export type ChunkingRunLinks = {
  self: string;
  documents: string;
  validation: string;
};

export type ChunkingRunSummary = {
  runId: string;
  status: string;
  profileId: string;
  requestedDocuments: number;
  completedDocuments: number;
  warnings: string[];
  links: ChunkingRunLinks;
};

export type ChunkingRunDocument = {
  documentId: string;
  status: string;
  reused: boolean;
  runId: string;
  normalizedRelpath: string;
};

export type ChunkingRunDocumentsPage = {
  items: ChunkingRunDocument[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

export type ChunkingStoredDocument = {
  documentId: string;
  normalizedRelpath: string;
  sourceRelpath: string;
  profileId: string;
  parentCount: number;
  childCount: number;
};

export type ChunkingStoredDocumentsPage = {
  items: ChunkingStoredDocument[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

export type ChunkingSourceSpan = {
  pageStart: number | null;
  pageEnd: number | null;
  charStart: number;
  charEnd: number;
};

export type ChunkingParentChunk = {
  chunkId: string;
  documentId: string;
  profileId: string;
  ordinal: number;
  text: string;
  sourceSpan: ChunkingSourceSpan;
  blockIds: string[];
};

export type ChunkingChildChunk = {
  chunkId: string;
  documentId: string;
  profileId: string;
  parentId: string;
  ordinal: number;
  contextPrefix: string;
  text: string;
  sourceSpan: ChunkingSourceSpan;
  tokenStart: number;
  tokenEnd: number;
  tokenCount: number;
  overlapPreviousTokens: number;
  overlapNextTokens: number;
  overlapPreviousSpan: {
    tokenStart: number;
    tokenEnd: number;
  } | null;
  overlapNextSpan: {
    tokenStart: number;
    tokenEnd: number;
  } | null;
  zeroOverlapReasons: string[];
  warnings: string[];
};

export type ChunkingParentsPage = {
  items: ChunkingParentChunk[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

export type ChunkingChildrenPage = {
  items: ChunkingChildChunk[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

export type ChunkingValidationCheck = Record<string, unknown>;

export type ChunkingValidation = {
  runId: string;
  status: string;
  documentsChecked: number;
  errors: number;
  warnings: number;
  checks: ChunkingValidationCheck[];
};

export type ChunkingErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    run_id?: string | null;
    details?: Record<string, unknown>;
  };
};
