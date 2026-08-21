"""Directorio local de operadores GUI con usuario y contraseña."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from dataclasses import dataclass

from pydantic import Field

from core.http_auth import HttpAuthInvalidCredentials, HttpAuthPrincipalExists
from ingestion.schemas.common import StrictModel


_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_DERIVED_KEY_BYTES = 32


class PersistedLocalOperator(StrictModel):
    username: str = Field(min_length=1)
    password_hash: str = Field(min_length=1)
    password_salt: str = Field(min_length=1)
    # None = operador global (sin recorte de proyectos). Campo con default para que
    # registros antiguos (previos al scope) rehidraten como globales sin migración.
    project_scope: tuple[str, ...] | None = None


class PersistedLocalOperatorDirectory(StrictModel):
    users: tuple[PersistedLocalOperator, ...] = ()


@dataclass(frozen=True)
class LocalOperatorAccount:
    username: str
    project_scope: tuple[str, ...] | None = None


class LocalOperatorDirectory:
    """Persist one small registry of GUI operators on local disk."""

    def __init__(self, registry_path: Path) -> None:
        self._registry_path = Path(registry_path)
        self._users = self._load_users()

    def register(
        self,
        *,
        username: str,
        password: str,
        project_scope: tuple[str, ...] | None = None,
    ) -> LocalOperatorAccount:
        normalized_username = _normalize_username(username)
        normalized_password = _normalize_password(password)
        normalized_scope = _normalize_scope(project_scope)
        if normalized_username in self._users:
            raise HttpAuthPrincipalExists(
                f"principal {normalized_username} already exists"
            )
        salt = os.urandom(_SALT_BYTES)
        user = PersistedLocalOperator(
            username=normalized_username,
            password_hash=_derive_password_hash(normalized_password, salt),
            password_salt=base64.b64encode(salt).decode("ascii"),
            project_scope=normalized_scope,
        )
        updated_users = dict(self._users)
        updated_users[normalized_username] = user
        self._persist_users(updated_users)
        self._users = updated_users
        return LocalOperatorAccount(
            username=normalized_username, project_scope=normalized_scope
        )

    def authenticate(self, *, username: str, password: str) -> LocalOperatorAccount:
        normalized_username = _normalize_username(username)
        normalized_password = _normalize_password(password)
        user = self._users.get(normalized_username)
        if user is None:
            raise HttpAuthInvalidCredentials("invalid username or password")
        salt = base64.b64decode(user.password_salt.encode("ascii"))
        expected_hash = _derive_password_hash(normalized_password, salt)
        if not hmac.compare_digest(expected_hash, user.password_hash):
            raise HttpAuthInvalidCredentials("invalid username or password")
        return LocalOperatorAccount(
            username=normalized_username, project_scope=user.project_scope
        )

    def _load_users(self) -> dict[str, PersistedLocalOperator]:
        if not self._registry_path.exists():
            return {}
        payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
        registry = PersistedLocalOperatorDirectory.model_validate(payload)
        users: dict[str, PersistedLocalOperator] = {}
        for user in registry.users:
            if user.username in users:
                raise ValueError(
                    f"{self._registry_path} contains duplicate usernames"
                )
            users[user.username] = user
        return users

    def _persist_users(self, users: dict[str, PersistedLocalOperator]) -> None:
        payload = PersistedLocalOperatorDirectory(
            users=tuple(sorted(users.values(), key=lambda item: item.username))
        ).model_dump(mode="json")
        _write_atomic_json(self._registry_path, payload)


def _normalize_username(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise ValueError("username is required")
    return normalized


def _normalize_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("password is required")
    return password


def _normalize_scope(
    project_scope: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Normaliza el scope declarado: sin vacíos, deduplicado y ordenado estable.

    ``None`` o vacío = operador global (sin recorte). El enforcement real vive
    server-side en FastAPI vía el bearer emitido con este scope; aquí solo se
    persiste la intención de recorte por proyecto.
    """

    if project_scope is None:
        return None
    cleaned = sorted({project.strip() for project in project_scope if project.strip()})
    return tuple(cleaned) or None


def _derive_password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_DERIVED_KEY_BYTES,
    ).hex()


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
