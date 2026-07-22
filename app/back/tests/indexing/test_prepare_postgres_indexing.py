from __future__ import annotations

from pathlib import Path

from scripts.indexing.prepare_postgres_indexing import (
    build_dsn_from_env,
    load_env_file,
    migration_files,
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


def test_migration_files_include_schema_before_seed() -> None:
    names = [path.name for path in migration_files(Path("migrations"))]

    assert names.index("20260722_indexing_profiles_pgvector.sql") < names.index(
        "20260722_seed_indexing_profiles.sql"
    )
