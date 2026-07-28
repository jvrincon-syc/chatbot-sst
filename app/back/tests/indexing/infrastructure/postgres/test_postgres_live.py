from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile, NormalizedDocumentBundle
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from ingestion.paths import ArtifactPaths
from indexing.application.profile_orchestrator import EmbeddingProfileOrchestrator
from indexing.application.use_cases.index_document import IndexDocumentUseCase
from indexing.domain.models import IndexableDocument, IndexingProfile, NormalizedArtifactRefs
from indexing.infrastructure.embeddings.factory import EmbeddingFactory
from indexing.infrastructure.embeddings.settings import EmbeddingSettings
from indexing.infrastructure.llama_index.pipeline_factory import (
    FilesystemBundleLoader,
    LlamaIndexingPort,
)
from indexing.infrastructure.postgres.normalized_document_repository import (
    PostgresNormalizedDocumentRepository,
)
from indexing.infrastructure.postgres.node_repository import PostgresNodeRepository
from indexing.infrastructure.postgres.profile_registry import PostgresProfileRegistry
from indexing.infrastructure.postgres.settings import PostgresIndexingSettings
from indexing.infrastructure.postgres.vector_repository import PostgresVectorRepository
from scripts.indexing.run_indexing import finalize_postgres_connection


pytestmark = pytest.mark.postgres_live

LIVE_DOCS_NORMALIZED_ROOT = Path("data/docs_normalized")
LIVE_SOURCE_RELPATH = (
    "convivencia_laboral/manual/1772036012249_syc_mrh03sstmanualdeconv.md"
)
LIVE_DOCUMENT_ID = "doc_c392ec7bf8d98194"
LIVE_PROFILE_ID = "local-bge-m3-v1"
LIVE_VECTOR_TABLE = "idx_vec_local_bge_m3_v1"


def test_postgres_live_requires_explicit_dsn() -> None:
    if not os.environ.get("SST_POSTGRES_DSN"):
        pytest.skip("SST_POSTGRES_DSN is required for live PostgreSQL checks")

    pytest.importorskip("psycopg2")


def test_postgres_live_chunks_embeds_and_indexes_a_real_normalized_document_with_bge(
    tmp_path: Path,
) -> None:
    if not os.environ.get("SST_POSTGRES_DSN"):
        pytest.skip("SST_POSTGRES_DSN is required for live PostgreSQL checks")

    pytest.importorskip("torch")
    pytest.importorskip("FlagEmbedding")
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import sql

    settings = PostgresIndexingSettings.from_env(os.environ)
    assert settings.dsn is not None

    normalized_document = _load_normalized_document()
    assert normalized_document.document_id == LIVE_DOCUMENT_ID
    assert normalized_document.normalized_relpath == LIVE_SOURCE_RELPATH

    chunks_root = tmp_path / "chunks"
    chunk_repository = FilesystemChunkBundleRepository(output_root=chunks_root)
    chunking_service = ChunkingOrchestrator(
        engine=LocalChunkingEngine(),
        bundle_repository=chunk_repository,
        run_repository=FilesystemRunRepository(output_root=chunks_root),
    )
    chunk_profile = ChunkingProfile.local_structural_v1()
    chunk_result = chunking_service.process_document(
        document=normalized_document,
        profile=chunk_profile,
    )
    assert chunk_result.validation.status == "passed"
    assert chunk_result.validation.parent_count > 0
    assert chunk_result.validation.child_count > 0

    connection = psycopg2.connect(settings.dsn)
    succeeded = False
    try:
        registry = PostgresProfileRegistry(connection)
        resolved_profile = registry.get(LIVE_PROFILE_ID)
        assert resolved_profile.active is True
        assert resolved_profile.embedding_provider == "bge"
        assert resolved_profile.embedding_model == "BAAI/bge-m3"
        assert resolved_profile.embedding_dimension == 1024
        assert resolved_profile.vector_table == LIVE_VECTOR_TABLE

        index_profile = IndexingProfile(
            profile_id=resolved_profile.profile_id,
            chunking_version=resolved_profile.chunking_version,
            embedding_provider=resolved_profile.embedding_provider,
            embedding_model=resolved_profile.embedding_model,
            embedding_dimension=resolved_profile.embedding_dimension,
            vector_store=resolved_profile.vector_table,
            metadata_schema_version=resolved_profile.metadata_schema_version,
        )
        indexable_document = _indexable_document(
            normalized_document=normalized_document,
            profile=index_profile,
        )
        indexer = LlamaIndexingPort(
            bundle_loader=FilesystemBundleLoader(chunks_root=chunks_root),
            normalized_document_repository=PostgresNormalizedDocumentRepository(
                connection
            ),
            node_repository=PostgresNodeRepository(connection),
            vector_repository=PostgresVectorRepository(connection),
            profile_orchestrator=EmbeddingProfileOrchestrator(registry),
            embedding_factory=EmbeddingFactory(
                settings=EmbeddingSettings.from_env(os.environ)
            ),
            storage_mode="postgres",
            ingestion_origin="local",
        )
        result = asyncio.run(IndexDocumentUseCase(indexer=indexer).index(indexable_document))
        succeeded = True
    finally:
        finalize_postgres_connection(connection, succeeded=succeeded)

    verification_connection = psycopg2.connect(settings.dsn)
    try:
        db_summary = _read_live_rows(
            verification_connection,
            document_id=indexable_document.document_id,
            vector_table=LIVE_VECTOR_TABLE,
            sql_module=sql,
        )
    finally:
        verification_connection.close()

    assert result.profile.profile_id == LIVE_PROFILE_ID
    assert result.indexed_parent_nodes == chunk_result.validation.parent_count
    assert result.indexed_child_nodes == chunk_result.validation.child_count
    assert db_summary["normalized_row"] is not None
    assert db_summary["normalized_row"]["source_relpath"] == normalized_document.source_relpath
    assert db_summary["normalized_row"]["processing_status"] == "processed"
    assert db_summary["normalized_row"]["corpus_version"] == normalized_document.corpus_version
    assert db_summary["node_rows"] == result.indexed_parent_nodes + result.indexed_child_nodes
    assert db_summary["node_roles"].get("parent", 0) == result.indexed_parent_nodes
    assert db_summary["node_roles"].get("child", 0) == result.indexed_child_nodes
    assert db_summary["vector_rows"] == result.indexed_child_nodes
    assert db_summary["other_vector_tables"] == []

    summary = {
        "chunk_run_id": chunk_result.run_id,
        "document_id": indexable_document.document_id,
        "source_relpath": normalized_document.source_relpath,
        "vector_table": LIVE_VECTOR_TABLE,
        "chunked_parents": chunk_result.validation.parent_count,
        "chunked_children": chunk_result.validation.child_count,
        "indexed_parents": result.indexed_parent_nodes,
        "indexed_children": result.indexed_child_nodes,
        "normalized_row": db_summary["normalized_row"],
        "node_roles": db_summary["node_roles"],
        "vector_rows": db_summary["vector_rows"],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _load_normalized_document() -> NormalizedDocumentBundle:
    return Schema2NormalizedDocumentSource(LIVE_DOCS_NORMALIZED_ROOT).load(
        LIVE_SOURCE_RELPATH
    )


def _indexable_document(
    *,
    normalized_document: NormalizedDocumentBundle,
    profile: IndexingProfile,
) -> IndexableDocument:
    artifact_paths = ArtifactPaths.for_source(normalized_document.source_relpath)
    return IndexableDocument(
        document_id=normalized_document.document_id,
        source_relpath=normalized_document.source_relpath,
        source_hash=normalized_document.source_hash,
        document_status="processed",
        artifacts=NormalizedArtifactRefs(
            markdown=artifact_paths.markdown,
            metadata=artifact_paths.metadata,
            pages=artifact_paths.pages,
            tables=artifact_paths.tables,
            forms=artifact_paths.forms,
        ),
        profile=profile,
    )


def _read_live_rows(
    connection: object,
    *,
    document_id: str,
    vector_table: str,
    sql_module: object,
) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_relpath, source_hash, ingestion_origin, corpus_version,
                   processing_status
              FROM indexing_normalized_documents
             WHERE document_id = %s
            """,
            (document_id,),
        )
        normalized_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT node_role, COUNT(*)::int
              FROM indexing_nodes
             WHERE document_id = %s
             GROUP BY node_role
            """,
            (document_id,),
        )
        node_roles = {str(role): int(count) for role, count in cursor.fetchall()}

        cursor.execute(
            """
            SELECT COUNT(*)::int
              FROM indexing_nodes
             WHERE document_id = %s
            """,
            (document_id,),
        )
        node_rows = int(cursor.fetchone()[0])

        cursor.execute(
            sql_module.SQL("SELECT COUNT(*)::int FROM {} WHERE document_id = %s").format(
                sql_module.Identifier(vector_table)
            ),
            (document_id,),
        )
        vector_rows = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT tablename
              FROM pg_tables
             WHERE schemaname = 'public'
               AND tablename LIKE 'idx_vec_%'
             ORDER BY tablename
            """
        )
        other_vector_tables: list[tuple[str, int]] = []
        for (table_name,) in cursor.fetchall():
            if table_name == vector_table:
                continue
            cursor.execute(
                sql_module.SQL(
                    "SELECT COUNT(*)::int FROM {} WHERE document_id = %s"
                ).format(sql_module.Identifier(table_name)),
                (document_id,),
            )
            count = int(cursor.fetchone()[0])
            if count:
                other_vector_tables.append((str(table_name), count))

    if normalized_row is None:
        raise AssertionError("normalized document row was not written")

    source_relpath, source_hash, ingestion_origin, corpus_version, processing_status = normalized_row
    return {
        "normalized_row": {
            "source_relpath": str(source_relpath),
            "source_hash": str(source_hash),
            "ingestion_origin": str(ingestion_origin),
            "corpus_version": str(corpus_version),
            "processing_status": str(processing_status),
        },
        "node_rows": node_rows,
        "node_roles": node_roles,
        "vector_rows": vector_rows,
        "other_vector_tables": other_vector_tables,
    }
