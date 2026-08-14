from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from core.logging.logger import configure_structured_logging  # noqa: E402


REQUIRED_BASE_TABLES = (
    "indexing_profiles",
    "indexing_targets",
    "chunk_bundles",
    "embedding_runs",
    "embedding_bundles",
    "embedding_bundle_chunks",
    "indexing_normalized_documents",
    "indexing_runs",
    "indexing_run_documents",
    "indexing_nodes",
    "readiness_checks",
    "retrieval_profiles",
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare PostgreSQL/pgvector indexing schema."
    )
    parser.add_argument("--env-file", default="secrets.env")
    parser.add_argument("--migrations-dir", default="migrations")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()
    logger.info(
        "postgres prepare started: migrations_dir=%s env_file=%s",
        args.migrations_dir,
        args.env_file,
    )
    try:
        env = load_env_file(Path(args.env_file))
        dsn = build_dsn_from_env(env)
        if not dsn:
            logger.warning("postgres prepare blocked: dsn_missing")
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "postgres_dsn_missing",
                    },
                    sort_keys=True,
                )
            )
            return 2
        summary = prepare_database(
            dsn=dsn,
            migrations=migration_files(Path(args.migrations_dir)),
        )
        logger.info(
            "postgres prepare finished: status=%s base_tables_present=%s active_profiles=%s vector_tables_ready=%s",
            summary["status"],
            summary["base_tables_present"],
            summary["active_profiles"],
            summary["vector_tables_ready"],
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["status"] == "prepared" else 1
    except Exception as error:
        logger.error("postgres prepare failed: %s", type(error).__name__)
        payload = {"status": "failed", "error_type": type(error).__name__}
        if args.debug:
            payload["error"] = _redact(str(error))
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file without expanding values."""

    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_inline_comment(value.strip()).strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        values[key] = value.strip()
    return values


def build_dsn_from_env(env: Mapping[str, str]) -> str | None:
    """Resolve a PostgreSQL DSN without inventing credentials."""

    explicit = env.get("SST_POSTGRES_DSN")
    if explicit:
        return explicit
    host = env.get("POSTGRES_HOST")
    database = env.get("POSTGRES_DB")
    user = env.get("POSTGRES_USER")
    if host and database and user:
        port = env.get("POSTGRES_PORT") or "5432"
        password = env.get("POSTGRES_PASSWORD") or ""
        auth = quote_plus(user)
        if password:
            auth = f"{auth}:{quote_plus(password)}"
        return f"postgresql://{auth}@{host}:{port}/{quote_plus(database)}"
    database_url = env.get("DATABASE_URL")
    if database_url:
        return database_url
    return None


def migration_files(migrations_dir: Path) -> list[Path]:
    """Return SQL migrations in deterministic order."""

    return sorted(migrations_dir.glob("*.sql"), key=lambda path: path.name)


def prepare_database(*, dsn: str, migrations: Sequence[Path]) -> dict[str, object]:
    """Apply migrations and verify PostgreSQL is ready for indexing writes."""

    import psycopg2
    from psycopg2.extensions import parse_dsn

    connection = psycopg2.connect(**parse_dsn(dsn))
    try:
        with connection:
            with connection.cursor() as cursor:
                for migration in migrations:
                    logging.getLogger(__name__).info(
                        "applying migration %s", migration.name
                    )
                    cursor.execute(migration.read_text(encoding="utf-8"))
                summary = _verification_summary(cursor=cursor, migrations=migrations)
        return summary
    finally:
        connection.close()


def _verification_summary(*, cursor: object, migrations: Sequence[Path]) -> dict[str, object]:
    cursor.execute(
        """
        SELECT COUNT(*)
          FROM unnest(%s::text[]) AS table_name
         WHERE to_regclass(table_name) IS NOT NULL
        """,
        (list(REQUIRED_BASE_TABLES),),
    )
    base_tables_present = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM indexing_profiles WHERE active = true")
    active_profiles = int(cursor.fetchone()[0])
    cursor.execute(
        """
        SELECT COUNT(*)
          FROM indexing_profiles
         WHERE active = true
           AND to_regclass(vector_table) IS NOT NULL
        """
    )
    vector_tables_ready = int(cursor.fetchone()[0])
    cursor.execute(
        """
        SELECT COUNT(*)
          FROM indexing_profiles AS profile
          JOIN indexing_targets AS target
            ON target.indexing_target_id = profile.default_indexing_target_id
         WHERE profile.active = true
           AND target.active = true
           AND target.postgres_schema = 'public'
           AND target.vector_table = profile.vector_table
           AND to_regclass(target.vector_table) IS NOT NULL
        """
    )
    active_targets_ready = int(cursor.fetchone()[0])
    status = (
        "prepared"
        if base_tables_present == len(REQUIRED_BASE_TABLES)
        and active_profiles > 0
        and vector_tables_ready == active_profiles
        and active_targets_ready == active_profiles
        else "failed"
    )
    return {
        "status": status,
        "applied_migrations": [path.name for path in migrations],
        "base_tables_present": base_tables_present,
        "required_base_tables": len(REQUIRED_BASE_TABLES),
        "active_profiles": active_profiles,
        "vector_tables_ready": vector_tables_ready,
        "active_targets_ready": active_targets_ready,
    }


def _strip_inline_comment(value: str) -> str:
    if value.startswith(("'", '"')):
        return value
    return re.sub(r"\s+#.*$", "", value)


def _redact(value: str) -> str:
    return re.sub(r"(postgres(?:ql)?://[^:\s]+:)[^@\s]+@", r"\1<redacted>@", value)


def _configure_logging() -> None:
    """Backward-compatible no-op for older imports."""
    return None


if __name__ == "__main__":
    raise SystemExit(main())
