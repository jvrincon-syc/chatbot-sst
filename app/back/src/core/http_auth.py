"""HTTP bearer authentication for the bundle-first FastAPI surface.

The main pipeline API is an operator/internal boundary. Every HTTP request must
present a configured bearer credential; no route infers identity from query/body
fields and no route stays public by accident when auth is missing.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
import secrets

from pydantic import Field

from ingestion.schemas.common import StrictModel


AUTH_CREDENTIALS_JSON_KEY = "SST_HTTP_AUTH_CREDENTIALS_JSON"


class AuthenticatedPrincipal(StrictModel):
    """Authenticated HTTP principal derived from a configured bearer token."""

    principal_id: str = Field(min_length=1)
    project_scope: tuple[str, ...] | None = None


class BearerCredential(StrictModel):
    """Configured bearer credential allowed to call the internal HTTP API."""

    principal_id: str = Field(min_length=1)
    token: str = Field(min_length=1)
    project_scope: tuple[str, ...] | None = None


class HttpAuthError(Exception):
    """Base error for the HTTP authentication boundary."""

    code = "HTTP_AUTH_ERROR"
    http_status = 401

    @property
    def response_headers(self) -> dict[str, str]:
        """Headers that must accompany the HTTP auth error."""

        return {"WWW-Authenticate": "Bearer"}


class HttpAuthNotConfigured(HttpAuthError):
    """The server has no configured bearer credentials for the HTTP API."""

    code = "HTTP_AUTH_NOT_CONFIGURED"
    http_status = 503

    @property
    def response_headers(self) -> dict[str, str]:
        return {}


class HttpAuthRequired(HttpAuthError):
    """The request omitted the bearer token or used the wrong scheme."""

    code = "HTTP_AUTH_REQUIRED"


class HttpAuthInvalidCredentials(HttpAuthError):
    """The request supplied a bearer token that is not configured."""

    code = "HTTP_AUTH_INVALID_CREDENTIALS"


class HttpProjectScopeForbidden(HttpAuthError):
    """The authenticated principal is outside the allowed project scope."""

    code = "HTTP_PROJECT_SCOPE_FORBIDDEN"
    http_status = 403

    @property
    def response_headers(self) -> dict[str, str]:
        return {}


class ConfiguredBearerAuth:
    """Authenticates requests against a server-controlled bearer registry."""

    def __init__(self, config: Mapping[str, str] | None = None) -> None:
        env = os.environ if config is None else config
        raw = (env.get(AUTH_CREDENTIALS_JSON_KEY) or "").strip()
        if not raw:
            self._credentials: tuple[BearerCredential, ...] = ()
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{AUTH_CREDENTIALS_JSON_KEY} must be valid JSON"
            ) from error
        if not isinstance(payload, list):
            raise ValueError(f"{AUTH_CREDENTIALS_JSON_KEY} must be a JSON array")
        credentials = tuple(BearerCredential.model_validate(item) for item in payload)
        seen_tokens: set[str] = set()
        for credential in credentials:
            if credential.token in seen_tokens:
                raise ValueError(
                    f"{AUTH_CREDENTIALS_JSON_KEY} contains duplicate bearer tokens"
                )
            seen_tokens.add(credential.token)
        self._credentials = credentials

    @property
    def configured(self) -> bool:
        """Whether the server has any configured bearer credentials."""

        return bool(self._credentials)

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        """Authenticate the request and return the configured principal."""

        if not self._credentials:
            raise HttpAuthNotConfigured("http bearer authentication is not configured")
        if not authorization:
            raise HttpAuthRequired("missing Authorization: Bearer header")
        scheme, _, raw_token = authorization.partition(" ")
        token = raw_token.strip()
        if scheme.lower() != "bearer" or not token:
            raise HttpAuthRequired("expected Authorization: Bearer <token>")
        for credential in self._credentials:
            if secrets.compare_digest(credential.token, token):
                return AuthenticatedPrincipal(
                    principal_id=credential.principal_id,
                    project_scope=credential.project_scope,
                )
        raise HttpAuthInvalidCredentials("invalid bearer token")


def project_in_scope(principal: AuthenticatedPrincipal, project_id: str) -> bool:
    """Return whether the principal may access the given project."""

    return principal.project_scope is None or project_id in principal.project_scope


def require_project_in_scope(
    principal: AuthenticatedPrincipal,
    project_id: str,
) -> None:
    """Fail closed when the principal is outside the authorized project scope."""

    if not project_in_scope(principal, project_id):
        raise HttpProjectScopeForbidden(
            f"principal {principal.principal_id} is not authorized for project {project_id}"
        )
