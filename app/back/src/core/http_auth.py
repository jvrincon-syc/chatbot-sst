"""HTTP bearer authentication for the bundle-first FastAPI surface.

The main pipeline API is an operator/internal boundary. Every HTTP request must
present a configured bearer credential; no route infers identity from query/body
fields and no route stays public by accident when auth is missing.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading

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


class PersistedBearerCredential(StrictModel):
    """One local GUI bearer persisted as a one-way token digest."""

    principal_id: str = Field(min_length=1)
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_scope: tuple[str, ...] | None = None


class PersistedBearerRegistry(StrictModel):
    """Runtime registry persisted for local GUI principals."""

    credentials: tuple[PersistedBearerCredential, ...] = ()


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


class HttpAuthPrincipalExists(HttpAuthError):
    """A local GUI registration tried to reuse an existing principal id."""

    code = "HTTP_AUTH_PRINCIPAL_EXISTS"
    http_status = 409

    @property
    def response_headers(self) -> dict[str, str]:
        return {}


class HttpProjectScopeForbidden(HttpAuthError):
    """The authenticated principal is outside the allowed project scope."""

    code = "HTTP_PROJECT_SCOPE_FORBIDDEN"
    http_status = 403

    @property
    def response_headers(self) -> dict[str, str]:
        return {}


class ConfiguredBearerAuth:
    """Authenticates requests against a server-controlled bearer registry."""

    def __init__(
        self,
        config: Mapping[str, str] | None = None,
        *,
        local_registry_path: Path | None = None,
    ) -> None:
        env = os.environ if config is None else config
        raw = (env.get(AUTH_CREDENTIALS_JSON_KEY) or "").strip()
        if not raw:
            credentials: tuple[BearerCredential, ...] = ()
        else:
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
        self._local_registry_path = (
            None if local_registry_path is None else Path(local_registry_path)
        )
        self._local_credentials = self._load_local_credentials()
        self._session_credentials: dict[str, BearerCredential] = {}
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        """Whether the server has any configured bearer credentials."""

        with self._lock:
            return bool(
                self._credentials
                or self._local_credentials
                or self._session_credentials
            )

    def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        """Authenticate the request and return the configured principal."""

        with self._lock:
            local_credentials = tuple(self._local_credentials.values())
            session_credentials = tuple(self._session_credentials.values())
        if not self._credentials and not local_credentials and not session_credentials:
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
        for credential in session_credentials:
            if secrets.compare_digest(credential.token, token):
                return AuthenticatedPrincipal(
                    principal_id=credential.principal_id,
                    project_scope=credential.project_scope,
                )
        token_sha256 = _token_sha256(token)
        for credential in local_credentials:
            if secrets.compare_digest(credential.token_sha256, token_sha256):
                return AuthenticatedPrincipal(
                    principal_id=credential.principal_id,
                    project_scope=credential.project_scope,
                )
        raise HttpAuthInvalidCredentials("invalid bearer token")

    def register_principal(
        self,
        *,
        principal_id: str,
        project_scope: tuple[str, ...] | None,
    ) -> BearerCredential:
        """Register one local GUI principal and return its new bearer credential."""

        normalized_principal_id = principal_id.strip()
        if not normalized_principal_id:
            raise ValueError("principal_id is required")
        static_principal_ids = {
            credential.principal_id for credential in self._credentials
        }
        static_tokens = {credential.token for credential in self._credentials}
        with self._lock:
            local_principal_ids = {
                credential.principal_id
                for credential in self._local_credentials.values()
            }
            if (
                normalized_principal_id in static_principal_ids
                or normalized_principal_id in local_principal_ids
            ):
                raise HttpAuthPrincipalExists(
                    f"principal {normalized_principal_id} already exists"
                )
            issued_token = self._issue_unique_token(
                static_tokens,
                session_tokens=set(self._session_credentials),
            )
            token_sha256 = _token_sha256(issued_token)
            credential = BearerCredential(
                principal_id=normalized_principal_id,
                token=issued_token,
                project_scope=project_scope,
            )
            persisted = PersistedBearerCredential(
                principal_id=normalized_principal_id,
                token_sha256=token_sha256,
                project_scope=project_scope,
            )
            updated_credentials = dict(self._local_credentials)
            updated_credentials[persisted.token_sha256] = persisted
            self._persist_local_credentials(updated_credentials)
            self._local_credentials = updated_credentials
            return credential

    def issue_session_credential(
        self,
        *,
        principal_id: str,
        project_scope: tuple[str, ...] | None,
    ) -> BearerCredential:
        """Issue one in-memory bearer for an already-authenticated GUI principal."""

        normalized_principal_id = principal_id.strip()
        if not normalized_principal_id:
            raise ValueError("principal_id is required")
        static_tokens = {credential.token for credential in self._credentials}
        with self._lock:
            issued_token = self._issue_unique_token(
                static_tokens,
                session_tokens=set(self._session_credentials),
            )
            credential = BearerCredential(
                principal_id=normalized_principal_id,
                token=issued_token,
                project_scope=project_scope,
            )
            self._session_credentials[issued_token] = credential
            return credential

    def revoke_session_credential(self, token: str) -> None:
        """Forget one in-memory GUI bearer issued for a browser session."""

        with self._lock:
            self._session_credentials.pop(token, None)

    def _issue_unique_token(
        self,
        static_tokens: set[str],
        *,
        session_tokens: set[str],
    ) -> str:
        while True:
            candidate = f"gui-{secrets.token_urlsafe(24)}"
            if (
                candidate in static_tokens
                or candidate in session_tokens
                or _token_sha256(candidate) in self._local_credentials
            ):
                continue
            return candidate

    def _load_local_credentials(self) -> dict[str, PersistedBearerCredential]:
        if self._local_registry_path is None or not self._local_registry_path.exists():
            return {}
        try:
            payload = json.loads(
                self._local_registry_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{self._local_registry_path} must be valid JSON"
            ) from error
        registry = PersistedBearerRegistry.model_validate(payload)
        credentials_by_hash: dict[str, PersistedBearerCredential] = {}
        static_principal_ids = {
            credential.principal_id for credential in self._credentials
        }
        for credential in registry.credentials:
            if credential.principal_id in static_principal_ids:
                raise ValueError(
                    f"{self._local_registry_path} reuses configured principal ids"
                )
            if credential.principal_id in {
                item.principal_id for item in credentials_by_hash.values()
            }:
                raise ValueError(
                    f"{self._local_registry_path} contains duplicate principal ids"
                )
            if credential.token_sha256 in credentials_by_hash:
                raise ValueError(
                    f"{self._local_registry_path} contains duplicate token hashes"
                )
            credentials_by_hash[credential.token_sha256] = credential
        return credentials_by_hash

    def _persist_local_credentials(
        self,
        credentials: dict[str, PersistedBearerCredential],
    ) -> None:
        if self._local_registry_path is None:
            return
        payload = PersistedBearerRegistry(
            credentials=tuple(
                sorted(credentials.values(), key=lambda item: item.principal_id)
            )
        ).model_dump(mode="json")
        _write_atomic_json(self._local_registry_path, payload)


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _write_atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        descriptor = -1
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temp_path.unlink(missing_ok=True)
        raise


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
