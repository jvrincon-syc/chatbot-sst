from __future__ import annotations

from dataclasses import dataclass

import pytest
from llama_index.core.schema import TextNode
from psycopg2 import extensions, sql

from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from indexing.infrastructure.postgres.vector_repository import (
    AppendOnlyVectorRecord,
    PostgresVectorRepository,
)


def test_replace_document_vectors_executes_composed_sql_without_fstrings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection=connection)

    repository.replace_document_vectors(
        document_id="doc-1",
        profile=_resolved_profile(vector_table="idx_vec_local_bge_m3_v1"),
        nodes=[
            TextNode(
                id_="child-1",
                text="Contenido SST",
                metadata={"document_id": "doc-1"},
            )
        ],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    assert isinstance(connection.executed[0].query, sql.Composed)
    rendered = _render(connection.executed[0].query, monkeypatch)
    assert 'DELETE FROM "idx_vec_local_bge_m3_v1"' in rendered


def test_append_bundle_vectors_uses_target_authoritative_qualified_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection=connection)

    repository.append_bundle_vectors(
        profile=_resolved_profile(vector_table="idx_vec_llama_bge_m3_v1"),
        indexing_target_id="target-idx-vec-llama-bge-m3-v1",
        records=[
            AppendOnlyVectorRecord(
                node_id="child-1",
                document_id="doc-1",
                embedding=[0.1, 0.2, 0.3],
                metadata={"document_id": "doc-1"},
                embedding_bundle_id="bundle-1",
                corpus_version="phase1",
                configuration_fingerprint="a" * 64,
                vector_checksum="sha256:vector",
                project_id="proj_alpha",
            )
        ],
    )

    insert_query = next(
        execution.query
        for execution in connection.executed
        if isinstance(execution.query, sql.Composed)
    )
    rendered = _render(insert_query, monkeypatch)

    assert 'INSERT INTO "public"."idx_vec_llama_bge_m3_v1"' in rendered


def test_bundle_first_vector_writes_fail_closed_on_catalog_profile_table_mismatch() -> None:
    connection = RecordingConnection(
        target_vector_table="idx_vec_other_profile_v1",
    )
    repository = PostgresVectorRepository(connection=connection)

    with pytest.raises(
        VectorStoreWriteError, match="indexing target/catalog table mismatch"
    ):
        repository.append_bundle_vectors(
            profile=_resolved_profile(vector_table="idx_vec_llama_bge_m3_v1"),
            indexing_target_id="target-idx-vec-llama-bge-m3-v1",
            records=[
                AppendOnlyVectorRecord(
                    node_id="child-1",
                    document_id="doc-1",
                    embedding=[0.1, 0.2, 0.3],
                    metadata={"document_id": "doc-1"},
                    embedding_bundle_id="bundle-1",
                    corpus_version="phase1",
                    configuration_fingerprint="a" * 64,
                    vector_checksum="sha256:vector",
                    project_id="proj_alpha",
                )
            ],
        )


def _render(query: sql.Composed, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(
        extensions,
        "quote_ident",
        lambda value, _context: '"' + str(value).replace('"', '""') + '"',
    )
    return query.as_string(object())


def _resolved_profile(*, vector_table: str) -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=3,
        distance_metric="cosine",
        vector_table=vector_table,
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )


@dataclass(frozen=True)
class QueryExecution:
    query: object
    params: tuple[object, ...] | None


class RecordingConnection:
    def __init__(self, *, target_vector_table: str = "idx_vec_llama_bge_m3_v1") -> None:
        self.executed: list[QueryExecution] = []
        self._target_vector_table = target_vector_table
        self._cursor = RecordingCursor(self)

    def cursor(self) -> "RecordingCursor":
        return self._cursor


class RecordingCursor:
    def __init__(self, connection: RecordingConnection) -> None:
        self._connection = connection
        self._fetchone_result = None
        self.rowcount = 0

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: object, params: tuple[object, ...] | None = None) -> None:
        self._connection.executed.append(QueryExecution(query=query, params=params))
        if isinstance(query, str) and "FROM indexing_profiles" in query:
            self._fetchone_result = {
                "profile_id": "llama-bge-m3-v1",
                "ingestion_origin": "llama_cloud",
                "chunking_version": "structure-aware-v1",
                "embedding_provider": "bge",
                "embedding_model": "BAAI/bge-m3",
                "embedding_dimension": 3,
                "distance_metric": "cosine",
                "vector_table": "idx_vec_llama_bge_m3_v1",
                "metadata_schema_version": "2.0",
                "active": True,
                "config_hash": "a" * 64,
            }
            return
        if isinstance(query, str) and "FROM indexing_targets" in query:
            self._fetchone_result = {
                "indexing_target_id": "target-idx-vec-llama-bge-m3-v1",
                "postgres_schema": "public",
                "vector_table": self._connection._target_vector_table,
                "distance_ops": "vector_cosine_ops",
                "storage_schema_version": "idx-vec-v1",
                "active": True,
                "created_at": None,
                "deprecated_at": None,
            }
            return
        self._fetchone_result = None

    def fetchone(self):
        return self._fetchone_result
