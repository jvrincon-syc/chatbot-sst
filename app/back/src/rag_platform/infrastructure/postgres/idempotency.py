"""Adaptador PostgreSQL de idempotencia (autoridad durable, Fase 7).

Refleja el esquema congelado por ``migrations/20260819_01_create_platform_idempotency.sql``
y nunca emite DDL, igual que el resto de adaptadores de ``rag_platform``. Toda
sentencia es parametrizada; el registro nunca guarda datos sensibles.

Reserva atómica: ``INSERT ... ON CONFLICT (key_hash) DO NOTHING RETURNING`` deja
que exactamente un llamador concurrente inserte la fila. Si no hay fila devuelta,
otro llamador ya reservó la clave y se lee su estado actual.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from rag_platform.application.idempotency import (
    IdempotencyRecord,
    IdempotencyStatus,
    ReserveOutcome,
)

_COLUMNS = (
    "key_hash",
    "action",
    "resource_id",
    "request_fingerprint",
    "actor_id",
    "status",
    "response_status",
    "result_json",
    "created_at",
    "completed_at",
)


class PostgresIdempotencyStore:
    """Lee y escribe ``platform_idempotency_records`` de forma atómica."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def reserve(self, record: IdempotencyRecord) -> ReserveOutcome:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO platform_idempotency_records ("
                " key_hash, action, resource_id, request_fingerprint, actor_id,"
                " status, response_status, result_json, created_at, completed_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (key_hash) DO NOTHING"
                " RETURNING key_hash",
                (
                    record.key_hash,
                    record.action,
                    record.resource_id,
                    record.request_fingerprint,
                    record.actor_id,
                    record.status.value,
                    record.response_status,
                    None,
                    record.created_at,
                    record.completed_at,
                ),
            )
            inserted = cursor.fetchone()
        # Commit inmediato: la reserva es una transición corta e independiente; no
        # se sostiene el BEGIN mientras corre un build costoso.
        self._commit()
        if inserted is not None:
            return ReserveOutcome(fresh=True, record=record)
        return ReserveOutcome(fresh=False, record=self._get(record.key_hash))

    def complete(
        self, *, key_hash: str, response_status: int, result_json: dict[str, Any]
    ) -> None:
        self._terminal(
            key_hash=key_hash,
            status=IdempotencyStatus.COMPLETED,
            response_status=response_status,
            result_json=result_json,
        )

    def fail(self, *, key_hash: str, response_status: int) -> None:
        self._terminal(
            key_hash=key_hash,
            status=IdempotencyStatus.FAILED,
            response_status=response_status,
            result_json=None,
        )

    def _terminal(
        self,
        *,
        key_hash: str,
        status: IdempotencyStatus,
        response_status: int,
        result_json: dict[str, Any] | None,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE platform_idempotency_records"
                " SET status = %s, response_status = %s, result_json = %s,"
                " completed_at = %s"
                " WHERE key_hash = %s",
                (
                    status.value,
                    response_status,
                    json.dumps(result_json) if result_json is not None else None,
                    datetime.now(timezone.utc),
                    key_hash,
                ),
            )
        self._commit()

    def _get(self, key_hash: str) -> IdempotencyRecord:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM platform_idempotency_records"
                " WHERE key_hash = %s",
                (key_hash,),
            )
            row = cursor.fetchone()
        if row is None:  # pragma: no cover - la fila acaba de existir en el INSERT.
            raise KeyError(key_hash)
        return _row_to_record(row)

    def _commit(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()


def _row_to_record(row) -> IdempotencyRecord:
    result_json = row[7]
    if isinstance(result_json, str):
        result_json = json.loads(result_json)
    return IdempotencyRecord(
        key_hash=str(row[0]),
        action=str(row[1]),
        resource_id=str(row[2]),
        request_fingerprint=str(row[3]),
        actor_id=str(row[4]),
        status=IdempotencyStatus(str(row[5])),
        response_status=row[6],
        result_json=result_json,
        created_at=row[8],
        completed_at=row[9],
    )
