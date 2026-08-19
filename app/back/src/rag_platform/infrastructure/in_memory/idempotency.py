"""Adaptador in-memory de idempotencia (tests y composición sin conexión).

Espeja la semántica atómica del adaptador PostgreSQL usando un ``threading.Lock``
para que la reserva sea un verdadero test-and-set: dos hilos con la misma clave
no obtienen ambos ``fresh=True``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any

from rag_platform.application.idempotency import (
    IdempotencyRecord,
    IdempotencyStatus,
    ReserveOutcome,
)


class InMemoryIdempotencyStore:
    """Almacén de idempotencia en memoria, atómico bajo lock."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def reserve(self, record: IdempotencyRecord) -> ReserveOutcome:
        with self._lock:
            existing = self._records.get(record.key_hash)
            if existing is not None:
                return ReserveOutcome(fresh=False, record=existing)
            self._records[record.key_hash] = record
            return ReserveOutcome(fresh=True, record=record)

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
        with self._lock:
            current = self._records[key_hash]
            self._records[key_hash] = current.model_copy(
                update={
                    "status": status,
                    "response_status": response_status,
                    "result_json": result_json,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
