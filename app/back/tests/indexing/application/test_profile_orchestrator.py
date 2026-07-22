from __future__ import annotations

import pytest

from indexing.application.profile_orchestrator import (
    EmbeddingProfileOrchestrator,
    InactiveProfileError,
    ProfileLaneMismatchError,
)
from indexing.domain.profiles import ResolvedIndexingProfile


class FakeRegistry:
    def __init__(self, profile: ResolvedIndexingProfile) -> None:
        self.profile = profile

    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        assert profile_id == self.profile.profile_id
        return self.profile


def _profile(*, origin: str = "llama_cloud", active: bool = True) -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id="llama-bge-m3-v1",
        ingestion_origin=origin,
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        distance_metric="cosine",
        vector_table="idx_vec_llama_bge_m3_v1",
        metadata_schema_version="2.0",
        active=active,
        config_hash="a" * 64,
    )


def test_orchestrator_returns_active_profile_for_matching_lane() -> None:
    result = EmbeddingProfileOrchestrator(FakeRegistry(_profile())).resolve(
        profile_id="llama-bge-m3-v1",
        ingestion_origin="llama_cloud",
    )

    assert result.embedding_provider == "bge"


def test_orchestrator_rejects_local_documents_for_llama_profile() -> None:
    with pytest.raises(ProfileLaneMismatchError):
        EmbeddingProfileOrchestrator(FakeRegistry(_profile())).resolve(
            profile_id="llama-bge-m3-v1",
            ingestion_origin="local",
        )


def test_orchestrator_rejects_inactive_profile() -> None:
    with pytest.raises(InactiveProfileError):
        EmbeddingProfileOrchestrator(FakeRegistry(_profile(active=False))).resolve(
            profile_id="llama-bge-m3-v1",
            ingestion_origin="llama_cloud",
        )
