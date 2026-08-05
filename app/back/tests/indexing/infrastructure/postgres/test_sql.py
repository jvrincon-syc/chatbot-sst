from __future__ import annotations

from pathlib import Path

from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.postgres.settings import PostgresIndexingSettings
from indexing.infrastructure.postgres.sql import create_vector_table_sql


def test_pgvector_migration_creates_profile_registry() -> None:
    sql = Path("migrations/20260722_indexing_profiles_pgvector.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE IF NOT EXISTS indexing_profiles" in sql
    assert "CREATE TABLE IF NOT EXISTS indexing_normalized_documents" in sql
    assert (
        "UNIQUE (ingestion_origin, embedding_provider, embedding_model, "
        "embedding_dimension, distance_metric, chunking_version)"
    ) in sql


def test_pgvector_migration_does_not_create_one_mixed_vector_table() -> None:
    sql = Path("migrations/20260722_indexing_profiles_pgvector.sql").read_text(
        encoding="utf-8"
    )

    assert "llama_index_vectors (" not in sql
    assert "profile vector tables are created through controlled migrations" in sql


def test_seed_migration_creates_current_embedding_profile_tables() -> None:
    sql = Path("migrations/20260722_seed_indexing_profiles.sql").read_text(
        encoding="utf-8"
    )

    assert "'local-bge-m3-v1'" in sql
    assert "'llama-bge-m3-v1'" in sql
    assert "'local-voyage-4-v1'" in sql
    assert "'llama-voyage-4-v1'" in sql
    assert "'local-cohere-embed-v4-v1'" in sql
    assert "'llama-cohere-embed-v4-v1'" in sql
    assert "CREATE TABLE IF NOT EXISTS idx_vec_local_bge_m3_v1" in sql
    assert "CREATE TABLE IF NOT EXISTS idx_vec_llama_bge_m3_v1" in sql
    assert "embedding vector(1024) NOT NULL" in sql
    assert "embedding vector(1536) NOT NULL" in sql


def test_vector_table_sql_uses_dimension_and_cosine_ops() -> None:
    profile = _profile(distance_metric="cosine")

    sql = create_vector_table_sql(profile)

    assert "CREATE TABLE IF NOT EXISTS idx_vec_llama_bge_m3_v1" in sql
    assert "embedding vector(1024) NOT NULL" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql


def test_vector_table_sql_uses_inner_product_ops() -> None:
    sql = create_vector_table_sql(_profile(distance_metric="inner_product"))

    assert "USING hnsw (embedding vector_ip_ops)" in sql


def test_postgres_settings_require_dsn_for_enabled_store() -> None:
    settings = PostgresIndexingSettings.from_env(
        {"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"}
    )

    assert settings.dsn == "postgresql://user:secret@localhost/sst"
    assert settings.is_configured is True


def test_postgres_settings_do_not_invent_missing_dsn() -> None:
    settings = PostgresIndexingSettings.from_env({})

    assert settings.dsn is None
    assert settings.is_configured is False


def _profile(*, distance_metric: str) -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric=distance_metric,
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )
