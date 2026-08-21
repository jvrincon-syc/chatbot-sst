import {
  getJson,
  postJson,
  type PipelineGetOptions,
  type PipelinePostOptions,
} from "../../shared/api/apiClient.js";

export type AuthenticatedOperatorSession = {
  authenticated: true;
  principal_id: string;
  project_scope: string[] | null;
};

export type OperatorCredentials = {
  username: string;
  password: string;
};

// El scope es opcional: omitido/vacío = operador global. El backend lo normaliza
// y el enforcement real vive en FastAPI vía el bearer emitido con ese scope.
export type OperatorRegistration = OperatorCredentials & {
  project_scope?: string[];
};

export type AnonymousOperatorSession = {
  authenticated: false;
};

export type OperatorSessionResponse =
  | AuthenticatedOperatorSession
  | AnonymousOperatorSession;

const AUTH_BASE = "/api/auth";

export function getOperatorSession(
  options?: PipelineGetOptions,
): Promise<OperatorSessionResponse> {
  return getJson<OperatorSessionResponse>(`${AUTH_BASE}/session`, options);
}

export function loginOperatorSession(
  body: OperatorCredentials,
  options?: PipelinePostOptions,
): Promise<AuthenticatedOperatorSession> {
  return postJson<AuthenticatedOperatorSession>(
    `${AUTH_BASE}/login`,
    body,
    options,
  );
}

export function registerOperatorSession(
  body: OperatorRegistration,
  options?: PipelinePostOptions,
): Promise<AuthenticatedOperatorSession> {
  return postJson<AuthenticatedOperatorSession>(
    `${AUTH_BASE}/register`,
    body,
    options,
  );
}

export function logoutOperatorSession(
  options?: PipelinePostOptions,
): Promise<AnonymousOperatorSession> {
  return postJson<AnonymousOperatorSession>(`${AUTH_BASE}/logout`, {}, options);
}
