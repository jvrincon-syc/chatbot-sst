from __future__ import annotations

import pytest
from llama_index.core.schema import TextNode

from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from indexing.infrastructure.postgres.vector_repository import (
    AppendOnlyVectorRecord,
    InMemoryVectorRepository,
    PostgresVectorRepository,
)


def test_vector_repository_rejects_embedding_count_mismatch(nodes) -> None:
    repository = InMemoryVectorRepository()

    with pytest.raises(VectorStoreWriteError):
        repository.replace_document_vectors(
            document_id="doc_1",
            profile=_profile(),
            nodes=nodes,
            embeddings=[],
        )


def test_vector_repository_rejects_embedding_dimension_mismatch(nodes) -> None:
    repository = InMemoryVectorRepository()

    with pytest.raises(VectorStoreWriteError):
        repository.replace_document_vectors(
            document_id="doc_1",
            profile=_profile(),
            nodes=nodes[:1],
            embeddings=[[0.1, 0.2]],
        )


def test_vector_repository_replaces_only_selected_profile_vectors(nodes) -> None:
    repository = InMemoryVectorRepository()
    profile = _profile()
    other_profile = profile.model_copy(
        update={
            "profile_id": "llama-voyage-v1",
            "embedding_provider": "voyage",
            "embedding_model": "voyage-4",
            "vector_table": "idx_vec_llama_voyage_v1",
        }
    )

    repository.replace_document_vectors(
        document_id="doc_1",
        profile=profile,
        nodes=nodes[:1],
        embeddings=[[0.1, 0.2, 0.3]],
    )
    repository.replace_document_vectors(
        document_id="doc_1",
        profile=other_profile,
        nodes=nodes[:1],
        embeddings=[[0.4, 0.5, 0.6]],
    )
    repository.replace_document_vectors(
        document_id="doc_1",
        profile=profile,
        nodes=nodes[1:],
        embeddings=[[0.7, 0.8, 0.9]],
    )

    assert repository.count(document_id="doc_1", profile=profile) == 1
    assert repository.count(document_id="doc_1", profile=other_profile) == 1


def test_postgres_vector_repository_inserts_bundle_vectors_inactive() -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection)

    repository.append_bundle_vectors(
        profile=_profile(),
        indexing_target_id="target-idx-vec-llama-bge-m3-v1",
        records=[
            AppendOnlyVectorRecord(
                node_id="child_1",
                document_id="doc_1",
                embedding=[0.1, 0.2, 0.3],
                metadata={"document_id": "doc_1"},
                embedding_bundle_id="bundle_1",
                corpus_version="phase1",
                configuration_fingerprint="a" * 64,
                vector_checksum="sha256:vector",
            )
        ],
    )

    assert "INSERT INTO idx_vec_llama_bge_m3_v1" in connection.cursor_obj.statements[0]
    assert "is_active" in connection.cursor_obj.statements[0]
    assert connection.cursor_obj.params[0][8] is False


def test_postgres_vector_repository_replaces_legacy_vectors_with_partial_conflict_target() -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection)

    repository.replace_document_vectors(
        document_id="doc_1",
        profile=_profile(),
        nodes=[
            TextNode(
                id_="child_1",
                text="Contenido SST",
                metadata={"document_id": "doc_1"},
            )
        ],
        embeddings=[[0.1, 0.2, 0.3]],
    )

    assert "ON CONFLICT (node_id) WHERE embedding_bundle_id IS NULL DO UPDATE SET" in (
        connection.cursor_obj.statements[1]
    )


def test_postgres_vector_repository_activates_bundle_transactionally() -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection)

    repository.activate_bundle(
        profile=_profile(),
        indexing_target_id="target-idx-vec-llama-bge-m3-v1",
        corpus_version="phase1",
        embedding_bundle_id="bundle_new",
    )

    statements = connection.cursor_obj.statements
    assert "is_active = false" in statements[0]
    assert "superseded_at = now()" in statements[0]
    assert "embedding_bundle_id <> %s" in statements[0]
    assert "is_active = true" in statements[1]
    assert "embedding_bundle_id = %s" in statements[1]


def test_postgres_vector_repository_rolls_back_to_previous_bundle() -> None:
    connection = RecordingConnection()
    repository = PostgresVectorRepository(connection)

    repository.rollback_to_bundle(
        profile=_profile(),
        indexing_target_id="target-idx-vec-llama-bge-m3-v1",
        corpus_version="phase1",
        current_embedding_bundle_id="bundle_new",
        previous_embedding_bundle_id="bundle_old",
    )

    statements = connection.cursor_obj.statements
    assert "embedding_bundle_id = %s" in statements[0]
    assert "is_active = false" in statements[0]
    assert "embedding_bundle_id = %s" in statements[1]
    assert "is_active = true" in statements[1]


def _profile() -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=3,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()

    def cursor(self) -> "RecordingCursor":
        return self.cursor_obj


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []
        self.rowcount = 0

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)
