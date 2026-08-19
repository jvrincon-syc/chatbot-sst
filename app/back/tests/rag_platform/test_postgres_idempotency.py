"""Contrato del adaptador PostgreSQL de idempotencia (Fase 7).

PostgreSQL es la **autoridad durable** de idempotencia, así que su contrato se
congela aquí, no solo el del adaptador in-memory:

- la reserva es un ``INSERT ... ON CONFLICT (key_hash) DO NOTHING RETURNING``
  atómico: si inserta, este llamador es el dueño (``fresh``); si no, lee el estado
  ya reservado;
- ``complete``/``fail`` emiten ``UPDATE`` parametrizados y hacen commit corto;
- el ``result_json`` nunca se escribe en la reserva y solo guarda el resultado
  terminal (dict serializado); jamás datos sensibles;
- la fila se mapea de vuelta a ``IdempotencyRecord`` (result_json string → dict).

El test marcado ``postgres_live`` prueba dos reservas **concurrentes** reales
sobre la BD: exactamente un llamador se convierte en dueño.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
from hashlib import sha256
import uuid

import pytest

from rag_platform.application.idempotency import (
    IdempotencyRecord,
    IdempotencyStatus,
)
from rag_platform.infrastructure.postgres.idempotency import PostgresIdempotencyStore


def _record(
    *,
    key_hash: str = "a" * 64,
    status: IdempotencyStatus = IdempotencyStatus.RESERVED,
) -> IdempotencyRecord:
    return IdempotencyRecord(
        key_hash=key_hash,
        action="build",
        resource_id="ragr_x",
        request_fingerprint="b" * 64,
        actor_id="op-1",
        status=status,
        created_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


# --------------------------------------------------------------------------- #
# Contrato con connection fake (determinista, sin BD)                          #
# --------------------------------------------------------------------------- #


def test_reserve_fresh_inserta_atomico_hace_commit_y_no_persiste_result_json() -> None:
    connection = RecordingConnection([{"fetchone": ("a" * 64,)}])

    outcome = PostgresIdempotencyStore(connection).reserve(_record())

    assert outcome.fresh is True
    statement = connection.cursor_obj.statements[0]
    assert "INSERT INTO platform_idempotency_records" in statement
    assert "ON CONFLICT (key_hash) DO NOTHING" in statement
    assert "RETURNING key_hash" in statement
    params = connection.cursor_obj.params[0]
    # 10 columnas parametrizadas (%s), nunca interpolación de strings.
    assert len(params) == 10
    # result_json (posición 7) NUNCA se escribe en la reserva.
    assert params[7] is None
    # Reserva = transición corta e independiente: commit inmediato.
    assert connection.commits == 1


def test_reserve_conflict_lee_el_estado_ya_reservado() -> None:
    completed_row = (
        "a" * 64,
        "build",
        "ragr_x",
        "b" * 64,
        "op-1",
        IdempotencyStatus.COMPLETED.value,
        200,
        json.dumps({"state": "published"}),
        datetime(2026, 8, 19, tzinfo=timezone.utc),
        datetime(2026, 8, 19, tzinfo=timezone.utc),
    )
    connection = RecordingConnection(
        [{"fetchone": None}, {"fetchone": completed_row}]
    )

    outcome = PostgresIdempotencyStore(connection).reserve(_record())

    assert outcome.fresh is False
    assert outcome.record.status is IdempotencyStatus.COMPLETED
    assert outcome.record.response_status == 200
    # result_json string de la BD se parsea a dict.
    assert outcome.record.result_json == {"state": "published"}
    select_statement = connection.cursor_obj.statements[1]
    assert "SELECT" in select_statement
    assert "WHERE key_hash = %s" in select_statement
    assert connection.cursor_obj.params[1] == ("a" * 64,)


def test_complete_actualiza_estado_serializa_result_json_y_commit() -> None:
    connection = RecordingConnection([{}])

    PostgresIdempotencyStore(connection).complete(
        key_hash="a" * 64,
        response_status=200,
        result_json={"state": "published"},
    )

    statement = connection.cursor_obj.statements[0]
    assert "UPDATE platform_idempotency_records" in statement
    assert "WHERE key_hash = %s" in statement
    params = connection.cursor_obj.params[0]
    assert params[0] == IdempotencyStatus.COMPLETED.value
    assert params[1] == 200
    assert params[2] == json.dumps({"state": "published"})
    assert params[4] == "a" * 64
    assert connection.commits == 1


def test_fail_marca_failed_sin_result_json() -> None:
    connection = RecordingConnection([{}])

    PostgresIdempotencyStore(connection).fail(key_hash="a" * 64, response_status=500)

    params = connection.cursor_obj.params[0]
    assert params[0] == IdempotencyStatus.FAILED.value
    assert params[1] == 500
    # fail nunca persiste result_json.
    assert params[2] is None
    assert connection.commits == 1


# --------------------------------------------------------------------------- #
# Concurrencia real (postgres_live): exactamente un dueño                       #
# --------------------------------------------------------------------------- #


@pytest.mark.postgres_live
def test_dos_reservas_concurrentes_reales_solo_un_dueno() -> None:
    dsn = (os.environ.get("SST_POSTGRES_DSN") or "").strip()
    if not dsn:
        pytest.skip("SST_POSTGRES_DSN no configurado")

    import psycopg2
    from psycopg2.extensions import parse_dsn

    key_hash = sha256(f"concurrency-{uuid.uuid4().hex}".encode("utf-8")).hexdigest()
    record = _record(key_hash=key_hash)
    barrier = threading.Barrier(2)
    outcomes: list[bool] = []
    lock = threading.Lock()

    def _reserve_once() -> None:
        connection = psycopg2.connect(**parse_dsn(dsn))
        try:
            store = PostgresIdempotencyStore(connection)
            barrier.wait(timeout=10)
            fresh = store.reserve(record).fresh
            with lock:
                outcomes.append(fresh)
        finally:
            connection.close()

    threads = [threading.Thread(target=_reserve_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    cleanup = psycopg2.connect(**parse_dsn(dsn))
    try:
        with cleanup.cursor() as cursor:
            cursor.execute(
                "DELETE FROM platform_idempotency_records WHERE key_hash = %s",
                (key_hash,),
            )
        cleanup.commit()
    finally:
        cleanup.close()

    # La PK + ON CONFLICT DO NOTHING garantiza un único INSERT ganador.
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1


# --------------------------------------------------------------------------- #
# Doble de conexión que registra sentencias, parámetros y commits              #
# --------------------------------------------------------------------------- #


class RecordingConnection:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.cursor_obj = RecordingCursor(responses)
        self.commits = 0

    def cursor(self) -> "RecordingCursor":
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


class RecordingCursor:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = list(responses)
        self._current: dict[str, object] = {}
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)
        self._current = self._responses.pop(0) if self._responses else {}

    def fetchone(self):
        return self._current.get("fetchone")
