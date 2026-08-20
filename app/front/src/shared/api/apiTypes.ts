export type PageOptions = {
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type PaginatedResponse<T> = {
  items: T[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

export type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    run_id?: string | null;
    details?: Record<string, unknown>;
  };
};

export type PipelineHttpError = Error & {
  status: number;
  code: string | null;
  runId: string | null;
  details: Record<string, unknown>;
};

export type PipelineUiError = {
  status: number | null;
  code: string;
  message: string;
  runId: string | null;
  details: Record<string, unknown>;
  retryable: boolean;
};
