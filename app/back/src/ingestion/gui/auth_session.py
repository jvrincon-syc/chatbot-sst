"""Sesión GUI local por cookie opaca para usuarios locales con contraseña."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.http_auth import ConfiguredBearerAuth
from ingestion.gui.local_operator_auth import (
    LocalOperatorAccount,
    LocalOperatorDirectory,
)

SESSION_COOKIE_NAME = "chatbot_sst_gui_session"
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class GuiSession:
    session_id: str
    principal_id: str
    project_scope: tuple[str, ...] | None
    bearer_credential: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at

    def public_metadata(self) -> dict[str, object]:
        return {
            "authenticated": True,
            "principal_id": self.principal_id,
            "project_scope": None if self.project_scope is None else list(self.project_scope),
        }


class GuiSessionStore:
    """Store en memoria de proceso de sesiones GUI, thread-safe."""

    def __init__(self, *, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, GuiSession] = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(seconds=ttl_seconds)

    def create(
        self,
        *,
        principal_id: str,
        project_scope: tuple[str, ...] | None,
        bearer_credential: str,
        now: datetime,
    ) -> GuiSession:
        session = GuiSession(
            session_id=secrets.token_urlsafe(32),
            principal_id=principal_id,
            project_scope=project_scope,
            bearer_credential=bearer_credential,
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def resolve(self, session_id: str, *, now: datetime) -> GuiSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired(now=now):
                del self._sessions[session_id]
                return None
            return session

    def revoke(self, session_id: str) -> GuiSession | None:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def purge_expired(self, *, now: datetime) -> tuple[GuiSession, ...]:
        with self._lock:
            expired = [
                session
                for session in self._sessions.values()
                if session.is_expired(now=now)
            ]
            for session in expired:
                del self._sessions[session.session_id]
            return tuple(expired)

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())


class GuiAuthCoordinator:
    """Une directorio local de usuarios, bearer interno y cookie GUI."""

    def __init__(
        self,
        *,
        authenticator: ConfiguredBearerAuth,
        store: GuiSessionStore,
        directory: LocalOperatorDirectory,
    ) -> None:
        self._authenticator = authenticator
        self._store = store
        self._directory = directory

    def login(self, *, username: str, password: str, now: datetime) -> GuiSession:
        account = self._directory.authenticate(username=username, password=password)
        return self._open_session(account, now=now)

    def register(
        self,
        *,
        username: str,
        password: str,
        project_scope: tuple[str, ...] | None = None,
        now: datetime,
    ) -> GuiSession:
        account = self._directory.register(
            username=username, password=password, project_scope=project_scope
        )
        return self._open_session(account, now=now)

    def _open_session(self, account: LocalOperatorAccount, *, now: datetime) -> GuiSession:
        # El scope del operador viaja del directorio → bearer emitido → sesión →
        # /api/platform/*: FastAPI lo aplica sin que el frontend lo re-declare.
        self._revoke_expired_sessions(now=now)
        credential = self._authenticator.issue_session_credential(
            principal_id=account.username,
            project_scope=account.project_scope,
        )
        return self._store.create(
            principal_id=account.username,
            project_scope=account.project_scope,
            bearer_credential=credential.token,
            now=now,
        )

    def resolve(self, session_id: str, *, now: datetime) -> GuiSession | None:
        self._revoke_expired_sessions(now=now)
        return self._store.resolve(session_id, now=now)

    def logout(self, session_id: str) -> None:
        session = self._store.revoke(session_id)
        if session is not None:
            self._authenticator.revoke_session_credential(session.bearer_credential)

    @property
    def cookie_max_age(self) -> int:
        return self._store.ttl_seconds

    def _revoke_expired_sessions(self, *, now: datetime) -> None:
        expired_sessions = self._store.purge_expired(now=now)
        for session in expired_sessions:
            self._authenticator.revoke_session_credential(session.bearer_credential)


def parse_cookie(cookie_header: str | None, name: str) -> str | None:
    if not cookie_header:
        return None
    for pair in cookie_header.split(";"):
        key, _, value = pair.strip().partition("=")
        if key == name:
            return value or None
    return None


def build_session_cookie(session_id: str, *, max_age: int) -> str:
    return (
        f"{SESSION_COOKIE_NAME}={session_id}; HttpOnly; SameSite=Strict; "
        f"Path=/; Max-Age={max_age}"
    )


def build_expired_cookie() -> str:
    return f"{SESSION_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
