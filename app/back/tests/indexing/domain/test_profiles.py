from __future__ import annotations

import pytest
from pydantic import ValidationError

from indexing.domain.models import IndexingProfile
from indexing.domain.profiles import (
    ResolvedIndexingProfile,
    resolved_profile_from_indexing_profile,
)


def test_profile_accepts_supported_embedding_provider_lane_and_table() -> None:
    profile = ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )

    assert profile.vector_table == "idx_vec_llama_bge_m3_v1"
    assert profile.embedding_dimension == 1024


@pytest.mark.parametrize("provider", ["mock", "bge", "voyage", "cohere"])
def test_profile_allows_current_embedding_provider_choices(provider: str) -> None:
    profile = ResolvedIndexingProfile(
        profile_id=f"llama-{provider}-v1",
        ingestion_origin="llama_cloud",
        chunking_version="structure-aware-v1",
        embedding_provider=provider,
        embedding_model="test-model",
        embedding_dimension=384,
        distance_metric="cosine",
        vector_table=f"idx_vec_llama_{provider}_v1",
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )

    assert profile.embedding_provider == provider


def test_profile_rejects_invalid_vector_table_name() -> None:
    with pytest.raises(ValidationError):
        ResolvedIndexingProfile(
            profile_id="bad",
            ingestion_origin="llama_cloud",
            chunking_version="structure-aware-v1",
            embedding_provider="bge",
            embedding_model="BAAI/bge-m3",
            embedding_dimension=1024,
            distance_metric="cosine",
            vector_table="public.bad;drop table x",
            metadata_schema_version="2.0",
            active=True,
            config_hash="a" * 64,
        )


def test_resolved_profile_preserves_local_normalized_origin() -> None:
    profile = IndexingProfile(
        profile_id="local-mock-v1",
        chunking_version="structure-aware-v1",
        embedding_provider="mock",
        embedding_model="deterministic",
        embedding_dimension=384,
        vector_store="memory",
        metadata_schema_version="2.0",
    )

    resolved = resolved_profile_from_indexing_profile(
        profile,
        ingestion_origin="local",
        distance_metric="cosine",
        active=True,
        config_hash="b" * 64,
    )

    assert resolved.ingestion_origin == "local"
    assert resolved.vector_table == "idx_vec_local_mock_v1"
