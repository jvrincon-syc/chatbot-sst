"""Idempotencia durable de mutaciones de release (Fase 7).

Las mutaciones de build/lifecycle (``build``/``validate``/``publish``/``retire``)
exigen ``Idempotency-Key``. La autoridad durable es PostgreSQL (adaptador en
``infrastructure/postgres/idempotency.py``); el puerto ``IdempotencyStore`` la
abstrae para que ni el router HTTP ni los casos de uso de negocio conozcan SQL.

Modelo (espeja la convención de embedding: clave + fingerprint durable, replay
devuelve el resultado ya persistido, conflicto de payload falla cerrado):

- ``reserve`` es **atómico**: solo un llamador concurrente se convierte en dueño
  (``FRESH``); el resto observa ``IN_PROGRESS`` o un estado terminal.
- el dueño ejecuta la operación real fuera de cualquier transacción larga (no se
  sostiene un ``BEGIN`` durante un build costoso) y luego ``complete``/``fail``.
- un replay con la misma clave y el mismo fingerprint devuelve el resultado
  terminal ya guardado, **sin** re-ejecutar la operación.
- un fingerprint distinto para la misma clave es ``IdempotencyKeyConflict``.

El ``result_json`` guardado contiene solo identificadores/hashes/estado no
sensibles (nunca texto de documento, vectores, secretos ni rutas absolutas).

Dirección de dependencias: solo puertos (Protocol), errores de dominio y tipos
estándar; ningún SDK ni cliente de BD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Callable, Protocol

from ingestion.schemas.common import StrictModel
from pydantic import Field
from rag_platform.domain.errors import (
    IdempotencyKeyConflict,
    IdempotencyOperationInProgress,
)


class IdempotencyStatus(str, Enum):
    """Estado durable de un registro de idempotencia."""

    RESERVED = "reserved"
    COMPLETED = "completed"
    FAILED = "failed"


class IdempotencyRecord(StrictModel):
    """Registro durable de una petición de mutación idempotente.

    ``result_json`` solo se llena en estados terminales y jamás contiene datos
    sensibles (solo ids/hashes/estado de la release).
    """

    key_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor_id: str = Field(min_length=1)
    status: IdempotencyStatus
    response_status: int | None = None
    result_json: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ReserveOutcome(StrictModel):
    """Resultado de un intento de reserva.

    ``fresh`` indica que este llamador ganó la reserva y debe ejecutar la
    operación. Si no es ``fresh``, ``record`` describe el estado ya existente.
    """

    fresh: bool
    record: IdempotencyRecord


class IdempotencyStore(Protocol):
    """Puerto durable de idempotencia (autoridad: PostgreSQL en Fase 7)."""

    def reserve(self, record: IdempotencyRecord) -> ReserveOutcome:
        """Reserva atómicamente ``record`` o devuelve el existente.

        Debe ser atómica frente a concurrencia: exactamente un llamador obtiene
        ``fresh=True`` para una ``key_hash`` dada.
        """

    def complete(
        self, *, key_hash: str, response_status: int, result_json: dict[str, Any]
    ) -> None:
        """Marca la reserva como ``COMPLETED`` con su resultado terminal."""

    def fail(self, *, key_hash: str, response_status: int) -> None:
        """Marca la reserva como ``FAILED`` (terminal)."""


class IdempotencyResult(StrictModel):
    """Resultado lógico terminal de una mutación protegida por idempotencia."""

    response_status: int
    result_json: dict[str, Any]
    replayed: bool


def idempotency_request_fingerprint(
    *, action: str, resource_id: str, actor_id: str
) -> str:
    """Fingerprint determinista de la petición lógica (principal + acción + recurso).

    Scope de idempotencia = ``actor_id + action + resource_id`` (principal
    incluido): dos principales distintos que reusen la misma ``Idempotency-Key``
    producen fingerprints distintos, de modo que un segundo actor jamás recibe el
    resultado replay del primero (ni salta su chequeo de autorización). Fail-closed
    de cara a SSO/RBAC. Solo incluye campos no sensibles; nunca contenido
    documental, vectores, secretos ni rutas.
    """

    payload = json.dumps(
        {"action": action, "resource_id": resource_id, "actor_id": actor_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _hash_key(idempotency_key: str) -> str:
    return sha256(idempotency_key.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyGuard:
    """Orquesta reserva → ejecución → terminal, sin tocar los casos de uso.

    El router pasa la operación como ``callable``; el guard nunca conoce la
    lógica de release. La operación se ejecuta **fuera** de la transacción de
    reserva (no se sostiene un ``BEGIN`` durante un build costoso).
    """

    def __init__(
        self, *, store: IdempotencyStore, clock: Callable[[], datetime] = _now
    ) -> None:
        self._store = store
        self._clock = clock

    def run(
        self,
        *,
        idempotency_key: str,
        action: str,
        resource_id: str,
        actor_id: str,
        response_status: int,
        operation: Callable[[], dict[str, Any]],
    ) -> IdempotencyResult:
        """Ejecuta ``operation`` una sola vez por clave/fingerprint.

        Args:
            idempotency_key: Valor crudo del header ``Idempotency-Key``.
            action: Acción lógica (``build``/``validate``/``publish``/``retire``).
            resource_id: ``rag_release_id`` objetivo.
            actor_id: Actor de confianza server-side (auditoría).
            response_status: HTTP status a devolver en éxito fresco.
            operation: Callable que ejecuta el caso de uso y devuelve un dict de
                resultado no sensible (ids/hashes/estado).

        Returns:
            El resultado terminal (fresco o reproducido).

        Raises:
            IdempotencyKeyConflict: Clave reusada para otra petición lógica.
            IdempotencyOperationInProgress: Otra ejecución con la misma clave sigue
                ``RESERVED`` (duplicado concurrente).
        """

        key_hash = _hash_key(idempotency_key)
        fingerprint = idempotency_request_fingerprint(
            action=action, resource_id=resource_id, actor_id=actor_id
        )
        reservation = self._store.reserve(
            IdempotencyRecord(
                key_hash=key_hash,
                action=action,
                resource_id=resource_id,
                request_fingerprint=fingerprint,
                actor_id=actor_id,
                status=IdempotencyStatus.RESERVED,
                created_at=self._clock(),
            )
        )

        if not reservation.fresh:
            existing = reservation.record
            if existing.request_fingerprint != fingerprint:
                # Misma clave, petición lógica distinta: fail-closed.
                raise IdempotencyKeyConflict(
                    f"idempotency key already maps to action {existing.action!r} "
                    f"on {existing.resource_id!r}"
                )
            if existing.status is IdempotencyStatus.RESERVED:
                # Duplicado concurrente: no arrancar una segunda transición.
                raise IdempotencyOperationInProgress(existing.resource_id)
            # Terminal (COMPLETED/FAILED): reproduce el resultado ya persistido.
            # ponytail: un RESERVED huérfano (proceso caído a mitad de build) queda
            # bloqueado hasta limpieza manual; reconcile por antigüedad si hace falta.
            return IdempotencyResult(
                response_status=existing.response_status or response_status,
                result_json=existing.result_json or {},
                replayed=True,
            )

        try:
            result_json = operation()
        except Exception:
            self._store.fail(key_hash=key_hash, response_status=500)
            raise
        self._store.complete(
            key_hash=key_hash,
            response_status=response_status,
            result_json=result_json,
        )
        return IdempotencyResult(
            response_status=response_status, result_json=result_json, replayed=False
        )
