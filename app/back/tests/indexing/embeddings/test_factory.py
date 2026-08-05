from __future__ import annotations

import pytest

from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.factory import (
    EmbeddingFactory,
    EmbeddingProfileMismatchError,
    UnknownEmbeddingProviderError,
)
from indexing.infrastructure.embeddings.settings import EmbeddingSettings


def _profile(
    *,
    provider: str = "mock",
    dimension: int = 3,
) -> IndexingProfile:
    return IndexingProfile(
        profile_id=f"{provider}-profile",
        chunking_version="structure-aware-v1",
        embedding_provider=provider,
        embedding_model="deterministic",
        embedding_dimension=dimension,
        vector_store="memory",
        metadata_schema_version="2.0",
    )


def test_embedding_factory_creates_deterministic_provider_for_tests() -> None:
    provider = EmbeddingFactory().create(_profile())

    batch = provider.embed_documents(["abc", "abd"])

    assert batch.provider == "mock"
    assert batch.model == "deterministic"
    assert batch.dimension == 3
    assert len(batch.vectors) == 2
    assert all(len(vector) == 3 for vector in batch.vectors)
    assert batch.vectors[0] != batch.vectors[1]
    assert provider.embed_texts(["abc"]) == provider.embed_documents(["abc"]).vectors


def test_embedding_factory_rejects_vector_store_dimension_mismatch() -> None:
    with pytest.raises(EmbeddingProfileMismatchError, match="dimension"):
        EmbeddingFactory(expected_dimension=4).create(_profile(dimension=3))


def test_embedding_factory_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownEmbeddingProviderError, match="unknown"):
        EmbeddingFactory().create(_profile(provider="unknown"))


def test_embedding_factory_builds_named_provider_adapters_without_importing_sdks() -> None:
    for provider_name in ("bge", "voyage", "cohere"):
        provider = EmbeddingFactory().create(
            _profile(provider=provider_name, dimension=1024)
        )

        assert provider.profile.embedding_provider == provider_name


def test_embedding_factory_reuses_provider_instances_for_same_profile() -> None:
    factory = EmbeddingFactory(settings=EmbeddingSettings(provider="mock"))

    first = factory.create(_profile())
    second = factory.create(_profile())

    assert first is second
