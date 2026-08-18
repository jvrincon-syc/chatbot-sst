from __future__ import annotations

from pathlib import Path

from scripts.indexing.prepare_postgres_indexing import migration_files


MIGRATIONS_DIR = Path("migrations")
TASK3_AND_4_MIGRATIONS = (
    "20260818_01_version_project_target_bindings.sql",
    "20260818_02_pin_release_configuration_version.sql",
    "20260818_03_enforce_release_configuration_pin.sql",
)


def test_clean_schema_upgrade_orders_binding_and_release_pin_migrations() -> None:
    names = [path.name for path in migration_files(MIGRATIONS_DIR)]

    assert names.index("20260810_07_create_rag_releases_and_memberships.sql") < names.index(
        TASK3_AND_4_MIGRATIONS[0]
    )
    assert names.index(TASK3_AND_4_MIGRATIONS[0]) < names.index(TASK3_AND_4_MIGRATIONS[1])
    assert names.index(TASK3_AND_4_MIGRATIONS[1]) < names.index(TASK3_AND_4_MIGRATIONS[2])


def test_upgrade_from_liveish_seed_to_head_covers_versioned_bindings_and_release_pin() -> None:
    sql = _upgrade_from_liveish_seed_to_head()

    assert "project_indexing_target_bindings" in sql
    assert "rag_releases" in sql
    assert "configuration_version" in sql
    assert "target_binding_key" in sql
    assert "NOT VALID" in sql
    assert "VALIDATE CONSTRAINT rag_releases_versioned_binding_fkey" in sql
    assert "ALTER COLUMN configuration_version SET NOT NULL" in sql


def test_liveish_upgrade_refuses_fabricated_history_and_backfills_only_deterministic_cases() -> None:
    version_bindings = _migration_text(TASK3_AND_4_MIGRATIONS[0])
    pin_releases = _migration_text(TASK3_AND_4_MIGRATIONS[1])
    enforce_pin = _migration_text(TASK3_AND_4_MIGRATIONS[2])

    assert "historical target binding mapping required before versioning" in version_bindings
    assert "HAVING count(*) <> 1" in version_bindings
    assert "min(version) AS version" in version_bindings
    assert "SIN BACKFILL FABRICADO" in pin_releases
    assert "max(version)" in pin_releases
    assert "VALIDATE CONSTRAINT rag_releases_configuration_version_required" in enforce_pin


def _upgrade_from_liveish_seed_to_head() -> str:
    return "\n".join(_migration_text(name) for name in TASK3_AND_4_MIGRATIONS)


def _migration_text(name: str) -> str:
    return (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
