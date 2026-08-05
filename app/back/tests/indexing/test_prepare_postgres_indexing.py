from __future__ import annotations

from pathlib import Path

import pytest

from scripts.indexing.prepare_postgres_indexing import (
    build_dsn_from_env,
    load_env_file,
    migration_files,
    prepare_database,
)


def test_load_env_file_parses_values_without_comments(tmp_path: Path) -> None:
    env_file = tmp_path / "secrets.env"
    env_file.write_text(
        """
        # PostgreSQL
        POSTGRES_HOST=localhost
        POSTGRES_PASSWORD=secret # comment
        HF_TOKEN =
        DATABASE_URL="postgresql://postgres:secret@localhost:5432/chatbot_sst"
        """,
        encoding="utf-8",
    )

    values = load_env_file(env_file)

    assert values["POSTGRES_HOST"] == "localhost"
    assert values["POSTGRES_PASSWORD"] == "secret"
    assert values["HF_TOKEN"] == ""
    assert values["DATABASE_URL"] == "postgresql://postgres:secret@localhost:5432/chatbot_sst"


def test_build_dsn_prefers_explicit_sst_postgres_dsn() -> None:
    dsn = build_dsn_from_env(
        {
            "SST_POSTGRES_DSN": "postgresql://explicit/db",
            "DATABASE_URL": "postgresql://fallback/db",
        }
    )

    assert dsn == "postgresql://explicit/db"


def test_build_dsn_falls_back_to_database_url() -> None:
    dsn = build_dsn_from_env({"DATABASE_URL": "postgresql://fallback/db"})

    assert dsn == "postgresql://fallback/db"


def test_build_dsn_prefers_split_postgres_credentials_over_database_url() -> None:
    dsn = build_dsn_from_env(
        {
            "DATABASE_URL": "postgresql://postgres@localhost:5432/chatbot_sst",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_DB": "chatbot_sst",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "secret",
            "POSTGRES_PORT": "5432",
        }
    )

    assert dsn == "postgresql://postgres:secret@localhost:5432/chatbot_sst"


def test_migration_files_include_schema_before_seed() -> None:
    names = [path.name for path in migration_files(Path("migrations"))]

    assert names.index("20260722_indexing_profiles_pgvector.sql") < names.index(
        "20260722_seed_indexing_profiles.sql"
    )


def test_prepare_database_uses_parsed_connection_kwargs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = tmp_path / "001_prepare.sql"
    migration.write_text("SELECT 1;", encoding="utf-8")
    captured: dict[str, str] = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr("psycopg2.connect", fake_connect)
    monkeypatch.setattr(
        "scripts.indexing.prepare_postgres_indexing._verification_summary",
        lambda *, cursor, migrations: {
            "status": "prepared",
            "applied_migrations": [path.name for path in migrations],
            "base_tables_present": 5,
            "required_base_tables": 5,
            "active_profiles": 1,
            "vector_tables_ready": 1,
        },
    )

    summary = prepare_database(
        dsn="postgresql://postgres:secret@localhost:5432/chatbot_sst",
        migrations=[migration],
    )

    assert captured["host"] == "localhost"
    assert captured["port"] == "5432"
    assert captured["dbname"] == "chatbot_sst"
    assert captured["user"] == "postgres"
    assert captured["password"] == "secret"
    assert summary["status"] == "prepared"


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> "FakeCursor":
        return FakeCursor()

    def close(self) -> None:
        pass


class FakeCursor:
    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        pass

    def fetchone(self):
        return (1,)
