from __future__ import annotations

import pytest

from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from indexing.infrastructure.postgres.vector_repository import InMemoryVectorRepository


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
