"""Upgrade test for ``20260805_16``: the dedicated profile verification kind.

The migration is applied by ``indexing:prepare-postgres`` like every other one.
These checks prove the constraint really widened, that real indexing readiness
rows were not reclassified, and that the documented logical rollback is lossless.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.postgres_live

MIGRATION = Path("migrations/20260805_16_add_embedding_profile_verification_check_kind.sql")
NEW_KIND = "embedding_profile_verification"


def _connection():
    if not os.environ.get("SST_POSTGRES_DSN"):
        pytest.skip("SST_POSTGRES_DSN is required for live PostgreSQL checks")
    psycopg2 = pytest.importorskip("psycopg2")
    return psycopg2.connect(os.environ["SST_POSTGRES_DSN"])


def test_la_migracion_existe_y_solo_amplia_el_catalogo() -> None:
    raw = MIGRATION.read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("--")
    )

    assert "readiness_checks_check_kind_check" in executable
    assert NEW_KIND in executable
    # One DROP CONSTRAINT, one ADD CONSTRAINT, one scoped UPDATE. Nothing else.
    assert executable.count("ALTER TABLE") == 2
    assert executable.count("ALTER TABLE readiness_checks") == 2
    assert executable.count("UPDATE ") == 1
    assert "UPDATE readiness_checks" in executable
    for forbidden in ("DROP TABLE", "DELETE", "TRUNCATE", "CREATE TABLE"):
        assert forbidden not in executable
    # The rollback must stay documented in the migration itself.
    assert "Logical rollback" in raw


def test_la_constraint_admite_el_nuevo_kind_tras_migrar() -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_get_constraintdef(oid)
                  FROM pg_constraint
                 WHERE conrelid = 'readiness_checks'::regclass
                   AND conname = 'readiness_checks_check_kind_check'
                """
            )
            row = cursor.fetchone()
        assert row is not None, "check_kind constraint is missing"
        definition = row[0]
        for kind in (
            "embedding_bundle_validation",
            NEW_KIND,
            "indexing_readiness",
            "retrieval_readiness",
        ):
            assert kind in definition
    finally:
        connection.close()


def test_acepta_y_revierte_una_fila_del_nuevo_kind() -> None:
    connection = _connection()
    report = {"subject_kind": "embedding_profile", "checks": []}
    check_id = "check-migration-upgrade-probe"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO readiness_checks (
                    check_id, check_kind, subject_id, status, validator_version, report_json
                )
                VALUES (%s, %s, %s, 'passed', 'embedding-validator-v1', %s::jsonb)
                ON CONFLICT (check_id) DO NOTHING
                """,
                (check_id, NEW_KIND, "probe-profile", json.dumps(report, sort_keys=True)),
            )
            cursor.execute(
                "SELECT check_kind FROM readiness_checks WHERE check_id = %s",
                (check_id,),
            )
            assert cursor.fetchone()[0] == NEW_KIND

            # Logical rollback of the data half, as documented in the migration.
            cursor.execute(
                "UPDATE readiness_checks SET check_kind = 'indexing_readiness'"
                " WHERE check_id = %s",
                (check_id,),
            )
            cursor.execute(
                "SELECT check_kind, report_json ->> 'subject_kind'"
                "  FROM readiness_checks WHERE check_id = %s",
                (check_id,),
            )
            kind, subject_kind = cursor.fetchone()
            assert kind == "indexing_readiness"
            assert subject_kind == "embedding_profile"
        connection.rollback()
    finally:
        connection.close()


def test_no_reclasifica_los_checks_reales_de_indexing() -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FROM readiness_checks
                 WHERE check_kind = %s
                   AND (report_json ->> 'subject_kind') IS DISTINCT FROM 'embedding_profile'
                """,
                (NEW_KIND,),
            )
            assert cursor.fetchone()[0] == 0
    finally:
        connection.close()
