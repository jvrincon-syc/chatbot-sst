from __future__ import annotations

import pytest

from indexing.infrastructure.postgres.profile_registry import (
    InMemoryProfileRegistry,
    ProfileNotFoundError,
)
from indexing.domain.profiles import ResolvedIndexingProfile


def test_profile_registry_returns_registered_profile() -> None:
    profile = _profile()
    registry = InMemoryProfileRegistry([profile])

    assert registry.get(profile.profile_id) == profile


def test_profile_registry_fails_closed_for_unknown_profile() -> None:
    registry = InMemoryProfileRegistry([])

    with pytest.raises(ProfileNotFoundError):
        registry.get("missing")


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
