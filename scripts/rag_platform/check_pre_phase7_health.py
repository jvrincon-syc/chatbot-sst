from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from core.logging.logger import configure_structured_logging  # noqa: E402
from scripts.indexing.prepare_postgres_indexing import (  # noqa: E402
    build_dsn_from_env,
    load_env_file,
)


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the read-only pre-Phase 7 health checks."
    )
    parser.add_argument("--env-file", default="secrets.env")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()
    env = load_env_file(Path(args.env_file))
    dsn = build_dsn_from_env(env)
    if not dsn:
        payload = {"status": "blocked", "reason": "postgres_dsn_missing"}
        _print(payload, as_json=args.json)
        return 2

    try:
        connection = _connect_readonly(dsn)
    except Exception as error:
        payload = {"status": "failed", "error_type": type(error).__name__}
        logger.error("pre-phase7 health checker failed to connect: %s", type(error).__name__)
        _print(payload, as_json=args.json)
        return 1

    try:
        report = run_pre_phase7_health_checks(connection=connection)
    finally:
        connection.close()
    _print(report, as_json=args.json)
    return 0 if report["status"] == "passed" else 2


def run_pre_phase7_health_checks(connection) -> dict[str, object]:
    """Run the read-only integrity checks required before Phase 7."""

    with connection.cursor() as cursor:
        checks = {
            "ownership": _fetchall(
                cursor,
                """
                /* pre_phase7_health:ownership */
                SELECT issue, table_name, row_count
                  FROM (
                        SELECT 'project_id_missing' AS issue,
                               'chunk_bundles' AS table_name,
                               count(*)::bigint AS row_count
                          FROM chunk_bundles
                         WHERE project_id IS NULL
                        UNION ALL
                        SELECT 'project_id_missing',
                               'embedding_bundles',
                               count(*)::bigint
                          FROM embedding_bundles
                         WHERE project_id IS NULL
                        UNION ALL
                        SELECT 'project_id_missing',
                               'embedding_runs',
                               count(*)::bigint
                          FROM embedding_runs
                         WHERE project_id IS NULL
                        UNION ALL
                        SELECT 'project_id_missing',
                               'indexing_runs',
                               count(*)::bigint
                          FROM indexing_runs
                         WHERE project_id IS NULL
                        UNION ALL
                        SELECT 'project_id_missing',
                               'indexing_nodes',
                               count(*)::bigint
                          FROM indexing_nodes
                         WHERE project_id IS NULL
                       ) AS failures
                 WHERE row_count > 0
                 ORDER BY table_name
                """,
            ),
            "orphans": _fetchall(
                cursor,
                """
                /* pre_phase7_health:orphans */
                SELECT issue, owner_id, referenced_id
                  FROM (
                        SELECT 'release_membership_chunk_bundle_missing' AS issue,
                               membership.rag_release_id AS owner_id,
                               membership.chunk_bundle_id AS referenced_id
                          FROM rag_release_memberships AS membership
                          LEFT JOIN chunk_bundles AS bundle
                            ON bundle.chunk_bundle_id = membership.chunk_bundle_id
                         WHERE membership.chunk_bundle_id IS NOT NULL
                           AND bundle.chunk_bundle_id IS NULL
                        UNION ALL
                        SELECT 'release_membership_embedding_bundle_missing',
                               membership.rag_release_id,
                               membership.embedding_bundle_id
                          FROM rag_release_memberships AS membership
                          LEFT JOIN embedding_bundles AS bundle
                            ON bundle.embedding_bundle_id = membership.embedding_bundle_id
                         WHERE membership.embedding_bundle_id IS NOT NULL
                           AND bundle.embedding_bundle_id IS NULL
                        UNION ALL
                        SELECT 'snapshot_document_revision_missing',
                               document.corpus_snapshot_id,
                               document.source_document_revision_id
                          FROM corpus_snapshot_documents AS document
                          LEFT JOIN source_document_revisions AS revision
                            ON revision.source_document_revision_id = document.source_document_revision_id
                         WHERE revision.source_document_revision_id IS NULL
                       ) AS failures
                 ORDER BY issue, owner_id
                """,
            ),
            "releases": _fetchall(
                cursor,
                """
                /* pre_phase7_health:releases */
                SELECT issue, rag_release_id, project_id, target_binding_key
                  FROM (
                        SELECT 'configuration_version_missing' AS issue,
                               release.rag_release_id,
                               release.project_id,
                               release.target_binding_key
                          FROM rag_releases AS release
                         WHERE release.configuration_version IS NULL
                        UNION ALL
                        SELECT 'versioned_binding_missing',
                               release.rag_release_id,
                               release.project_id,
                               release.target_binding_key
                          FROM rag_releases AS release
                          LEFT JOIN project_indexing_target_bindings AS binding
                            ON binding.project_id = release.project_id
                           AND binding.configuration_version = release.configuration_version
                           AND binding.binding_key = release.target_binding_key
                         WHERE release.configuration_version IS NOT NULL
                           AND binding.binding_key IS NULL
                       ) AS failures
                 ORDER BY rag_release_id
                """,
            ),
            "runs": _fetchall(
                cursor,
                """
                /* pre_phase7_health:runs */
                SELECT issue, run_id, status
                  FROM (
                        SELECT 'completed_embedding_run_without_bundle' AS issue,
                               embedding_run_id AS run_id,
                               status
                          FROM embedding_runs
                         WHERE status = 'completed'
                           AND produced_embedding_bundle_id IS NULL
                        UNION ALL
                        SELECT 'completed_indexing_run_without_target',
                               run_id,
                               status
                          FROM indexing_runs
                         WHERE status = 'completed'
                           AND (
                               indexing_target_id IS NULL
                               OR embedding_bundle_id IS NULL
                               OR corpus_version IS NULL
                           )
                       ) AS failures
                 ORDER BY run_id
                """,
            ),
            "materializations": _fetchall(
                cursor,
                """
                /* pre_phase7_health:materializations */
                SELECT issue, embedding_bundle_id, status
                  FROM (
                        SELECT 'sealed_bundle_without_chunk_rows' AS issue,
                               bundle.embedding_bundle_id,
                               bundle.status
                          FROM embedding_bundles AS bundle
                         WHERE bundle.status = 'sealed'
                           AND NOT EXISTS (
                               SELECT 1
                                 FROM embedding_bundle_chunks AS chunk
                                WHERE chunk.embedding_bundle_id = bundle.embedding_bundle_id
                           )
                        UNION ALL
                        SELECT 'ready_bundle_without_vector_count',
                               bundle.embedding_bundle_id,
                               bundle.readiness_status
                          FROM embedding_bundles AS bundle
                         WHERE bundle.readiness_status = 'ready'
                           AND coalesce(bundle.vector_count, 0) = 0
                       ) AS failures
                 ORDER BY embedding_bundle_id
                """,
            ),
            "vectors": _fetchall(
                cursor,
                """
                /* pre_phase7_health:vectors */
                SELECT issue, profile_id, indexing_target_id, target_relation
                  FROM (
                        SELECT CASE
                                   WHEN target.vector_table <> profile.vector_table
                                       THEN 'catalog_profile_table_mismatch'
                                   ELSE 'missing_vector_table'
                               END AS issue,
                               profile.profile_id,
                               target.indexing_target_id,
                               target.postgres_schema || '.' || target.vector_table AS target_relation
                          FROM indexing_profiles AS profile
                          JOIN indexing_targets AS target
                            ON target.indexing_target_id = profile.default_indexing_target_id
                         WHERE profile.active = true
                           AND target.active = true
                           AND (
                               target.vector_table <> profile.vector_table
                               OR to_regclass(
                                   format('%I.%I', target.postgres_schema, target.vector_table)
                               ) IS NULL
                           )
                       ) AS failures
                 ORDER BY profile_id
                """,
            ),
            "project_mismatches": _fetchall(
                cursor,
                """
                /* pre_phase7_health:project_mismatches */
                SELECT issue, owner_id, expected_project_id, actual_project_id
                  FROM (
                        SELECT 'release_variant_project_mismatch' AS issue,
                               release.rag_release_id AS owner_id,
                               release.project_id AS expected_project_id,
                               variant.project_id AS actual_project_id
                          FROM rag_releases AS release
                          JOIN rag_variants AS variant
                            ON variant.rag_variant_id = release.rag_variant_id
                         WHERE variant.project_id <> release.project_id
                        UNION ALL
                        SELECT 'release_snapshot_project_mismatch',
                               release.rag_release_id,
                               release.project_id,
                               snapshot.project_id
                          FROM rag_releases AS release
                          JOIN corpus_snapshots AS snapshot
                            ON snapshot.corpus_snapshot_id = release.corpus_snapshot_id
                         WHERE snapshot.project_id <> release.project_id
                        UNION ALL
                        SELECT 'embedding_bundle_chunk_bundle_project_mismatch',
                               bundle.embedding_bundle_id,
                               bundle.project_id,
                               chunk.project_id
                          FROM embedding_bundles AS bundle
                          JOIN chunk_bundles AS chunk
                            ON chunk.chunk_bundle_id = bundle.source_chunk_bundle_id
                         WHERE chunk.project_id <> bundle.project_id
                       ) AS failures
                 ORDER BY issue, owner_id
                """,
            ),
        }
    status = "blocked" if any(checks.values()) else "passed"
    return {"status": status, "checks": checks}


def _fetchall(cursor, statement: str) -> list[dict[str, object]]:
    cursor.execute(statement)
    rows = cursor.fetchall()
    return [dict(row) if isinstance(row, Mapping) else row for row in rows]


def _connect_readonly(dsn: str):
    import psycopg2
    from psycopg2.extensions import parse_dsn
    from psycopg2.extras import RealDictCursor

    connection = psycopg2.connect(**parse_dsn(dsn), cursor_factory=RealDictCursor)
    connection.set_session(readonly=True, autocommit=True)
    return connection


def _print(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
