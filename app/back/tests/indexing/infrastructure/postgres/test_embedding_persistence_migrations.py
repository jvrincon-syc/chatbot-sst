from __future__ import annotations

from pathlib import Path


MIGRATIONS_DIR = Path("migrations")


EXPECTED_MIGRATIONS = [
    "20260805_01_extend_indexing_profiles.sql",
    "20260805_02_create_indexing_targets.sql",
    "20260805_03_backfill_indexing_targets.sql",
    "20260805_04_create_chunk_bundles.sql",
    "20260805_05_create_embedding_runs.sql",
    "20260805_06_create_embedding_bundles.sql",
    "20260805_07_create_embedding_bundle_chunks.sql",
    "20260805_08_extend_indexing_runs.sql",
    "20260805_09_complete_indexing_run_documents.sql",
    "20260805_10_extend_indexing_nodes.sql",
    "20260805_11_extend_idx_vec_tables.sql",
    "20260805_12_create_readiness_checks.sql",
    "20260805_13_create_retrieval_profiles.sql",
    "20260805_14_backfill_legacy.sql",
    "20260805_15_activate_strong_constraints.sql",
]


VECTOR_TABLES = [
    "idx_vec_llama_first_local_v1",
    "idx_vec_local_bge_m3_v1",
    "idx_vec_llama_bge_m3_v1",
    "idx_vec_local_voyage_4_v1",
    "idx_vec_llama_voyage_4_v1",
    "idx_vec_local_cohere_embed_v4_v1",
    "idx_vec_llama_cohere_embed_v4_v1",
]


def test_embedding_persistence_migrations_exist_in_required_order() -> None:
    names = [path.name for path in sorted(MIGRATIONS_DIR.glob("*.sql"))]

    positions = [names.index(name) for name in EXPECTED_MIGRATIONS]

    assert positions == sorted(positions)


def test_new_schema_tables_define_bundle_first_lineage() -> None:
    sql = _migration_text()

    for table_name in (
        "indexing_targets",
        "chunk_bundles",
        "embedding_runs",
        "embedding_bundles",
        "embedding_bundle_chunks",
        "readiness_checks",
        "retrieval_profiles",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for column_name in (
        "configuration_fingerprint",
        "source_chunk_bundle_id",
        "embedding_bundle_id",
        "indexing_target_id",
        "compatibility_status",
        "validation_status",
        "activation_status",
    ):
        assert column_name in sql

    assert "UNIQUE (postgres_schema, vector_table)" in sql
    assert "UNIQUE (idempotency_key, request_fingerprint)" in sql
    assert "UNIQUE (" in sql
    normalized_sql = " ".join(sql.split())
    assert "source_chunk_bundle_id, embedding_profile_id, configuration_fingerprint" in normalized_sql
    assert "WHERE active = true" in sql


def test_each_profile_vector_table_gets_append_only_columns_and_indexes() -> None:
    sql = (MIGRATIONS_DIR / "20260805_11_extend_idx_vec_tables.sql").read_text(
        encoding="utf-8"
    )

    for table_name in VECTOR_TABLES:
        assert table_name in sql

    for index_template in (
        "idx_%s_embedding_bundle",
        "idx_%s_document_active",
        "idx_%s_profile_corpus_active",
        "idx_%s_target_corpus_active",
    ):
        assert index_template in sql

    for required_column in (
        "embedding_bundle_id",
        "embedding_profile_id",
        "indexing_target_id",
        "corpus_version",
        "configuration_fingerprint",
        "vector_checksum",
        "is_active",
        "superseded_at",
    ):
        assert required_column in sql


def test_strong_constraints_are_deferred_to_final_migration() -> None:
    sql = (MIGRATIONS_DIR / "20260805_15_activate_strong_constraints.sql").read_text(
        encoding="utf-8"
    )

    assert "embedding_bundle_status_complete" in sql
    assert "embedding_bundle_chunks_checksum_when_sealed" in sql
    assert "legacy_unverified" in sql
    assert "compatibility_not_proven" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in sql


def _migration_text() -> str:
    return "\n".join(
        (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
        for name in EXPECTED_MIGRATIONS
    )
