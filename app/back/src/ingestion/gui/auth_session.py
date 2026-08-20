"""Sesión GUI local de operador por cookie opaca (Gate 3, Fase 8).

El browser nunca posee el bearer: hace ``login`` con el token una vez, el servidor
lo valida contra la **misma** ``ConfiguredBearerAuth`` que FastAPI y guarda una
sesión en memoria de proceso indexada por un id opaco. El bridge resuelve la
cookie y **inyecta el bearer server-side** en las peticiones ``/api/platform/*``;
FastAPI vuelve a autenticar y autorizar igual que en Fase 7 (frontera de confianza
intacta). Sin persistir en archivos, sin loggear el bearer.

Ceiling (ponytail): store monoproceso con lock, TTL fijo, sin rotación. Es
correcto para una GUI local; un despliegue multiproceso pediría un store
compartido y se documentaría en un ADR.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.http_auth import ConfiguredBearerAuth

#: Nombre de la cookie de sesión (opaca, HttpOnly, SameSite=Strict).
SESSION_COOKIE_NAME = "chatbot_sst_gui_session"
#: TTL por defecto de una sesión GUI (12 h).
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class GuiSession:
    """Sesión GUI viva: identidad pública + bearer server-side (nunca al browser)."""

    session_id: str
    principal_id: str
    project_scope: tuple[str, ...] | None
    bearer_credential: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at

    def public_metadata(self) -> dict[str, object]:
        """Metadata pública (sin bearer): lo único que cruza al browser."""

        return {
            "authenticated": True,
            "principal_id": self.principal_id,
            "project_scope": (
                None if self.project_scope is None else list(self.project_scope)
            ),
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
        """Devuelve la sesión viva o ``None``; purga la entrada si expiró."""

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired(now=now):
                # Fail-closed: una sesión expirada se elimina y no autoriza nada.
                del self._sessions[session_id]
                return None
            return session

    def revoke(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def purge_expired(self, *, now: datetime) -> None:
        with self._lock:
            expired = [
                sid
                for sid, session in self._sessions.items()
                if session.is_expired(now=now)
            ]
            for sid in expired:
                del self._sessions[sid]

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())


class GuiAuthCoordinator:
    """Une la validación de token (``ConfiguredBearerAuth``) con el store de sesión."""

    def __init__(
        self,
        *,
        authenticator: ConfiguredBearerAuth,
        store: GuiSessionStore,
    ) -> None:
        self._authenticator = authenticator
        self._store = store

    def login(self, token: str, *, now: datetime) -> GuiSession:
        """Valida el token y crea una sesión. Propaga ``HttpAuthError`` si falla.

        El token se valida con la misma autoridad que FastAPI (compare constant-time)
        y se guarda como bearer server-side para inyectarlo luego; nunca vuelve al
        browser ni se loggea.
        """

        principal = self._authenticator.authenticate(f"Bearer {token}")
        # Barrido oportunista de expiradas en cada login (n pequeño en GUI local).
        self._store.purge_expired(now=now)
        return self._store.create(
            principal_id=principal.principal_id,
            project_scope=principal.project_scope,
            bearer_credential=token,
            now=now,
        )

    def resolve(self, session_id: str, *, now: datetime) -> GuiSession | None:
        return self._store.resolve(session_id, now=now)

    def logout(self, session_id: str) -> None:
        self._store.revoke(session_id)

    @property
    def cookie_max_age(self) -> int:
        return self._store.ttl_seconds


def parse_cookie(cookie_header: str | None, name: str) -> str | None:
    """Extrae el valor de una cookie por nombre de un header ``Cookie`` crudo.

    Parser mínimo (stdlib ``SimpleCookie`` toleraría metadatos que no necesitamos):
    separa por ``;`` y ``=``. Devuelve ``None`` si no está.
    """

    if not cookie_header:
        return None
    for pair in cookie_header.split(";"):
        key, _, value = pair.strip().partition("=")
        if key == name:
            return value or None
    return None


def build_session_cookie(session_id: str, *, max_age: int) -> str:
    """Construye el ``Set-Cookie`` opaco, HttpOnly y SameSite=Strict.

    Sin ``Secure`` porque la GUI local corre sobre ``http://127.0.0.1``; en un
    despliegue TLS se añadiría (ADR).
    """

    return (
        f"{SESSION_COOKIE_NAME}={session_id}; HttpOnly; SameSite=Strict; "
        f"Path=/; Max-Age={max_age}"
    )


def build_expired_cookie() -> str:
    """``Set-Cookie`` que expira la cookie de sesión (logout)."""

    return f"{SESSION_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
