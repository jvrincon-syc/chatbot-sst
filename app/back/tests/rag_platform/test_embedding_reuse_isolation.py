"""Fase 4: reuso de embedding bundle por identidad exacta con revalidación.

Cierra la deuda de Fase 3-b: además de la identidad física (que incluye
``project_id``), el reuso revalida dimensión y métrica y falla cerrado si difieren.
"""

from __future__ import annotations

import pytest

from rag_platform.application.artifact_reuse_service import ArtifactReusePolicy
from rag_platform.domain.errors import MaterializationValidationFailed
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import SealedEmbeddingBundle
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryChunkBundleReuseRepository,
    InMemoryNormalizedArtifactRepository,
    InMemorySealedEmbeddingBundleRepository,
)


_PROJECT_A = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_PROJECT_B = PlatformId(IdentityKind.PROJECT, "proj_beta")
_PROFILE = "profile_bge_m3"
_CONFIG_FP = "c" * 64


def _bundle(project: PlatformId) -> SealedEmbeddingBundle:
    return SealedEmbeddingBundle(
        embedding_bundle_id="eb_01",
        project_id=project,
        source_chunk_bundle_id="cb_01",
        bundle_dir_relpath="embeddings/eb_01",
        checksums={"vectors.jsonl": "d" * 64},
        dimension=1024,
        distance_metric="cosine",
        vector_count=2,
    )


def _policy() -> tuple[ArtifactReusePolicy, InMemorySealedEmbeddingBundleRepository]:
    embedding_repo = InMemorySealedEmbeddingBundleRepository()
    policy = ArtifactReusePolicy(
        normalized_repository=InMemoryNormalizedArtifactRepository(),
        chunk_bundle_repository=InMemoryChunkBundleReuseRepository(),
        embedding_bundle_repository=embedding_repo,
    )
    return policy, embedding_repo


def test_reutiliza_embedding_bundle_cuando_identidad_exacta_en_mismo_proyecto() -> None:
    policy, repo = _policy()
    repo.register_sealed(
        _bundle(_PROJECT_A),
        embedding_profile_id=_PROFILE,
        configuration_fingerprint=_CONFIG_FP,
    )

    reused = policy.find_reusable_embedding_bundle(
        project_id=_PROJECT_A,
        source_chunk_bundle_id="cb_01",
        embedding_profile_id=_PROFILE,
        configuration_fingerprint=_CONFIG_FP,
        expected_dimension=1024,
        expected_metric="cosine",
    )

    assert reused is not None
    assert reused.embedding_bundle_id == "eb_01"


def test_no_reutiliza_embedding_bundle_de_otro_proyecto() -> None:
    policy, repo = _policy()
    repo.register_sealed(
        _bundle(_PROJECT_B),
        embedding_profile_id=_PROFILE,
        configuration_fingerprint=_CONFIG_FP,
    )

    # Mismo chunk bundle/perfil/fingerprint pero otro proyecto => no coincide.
    assert (
        policy.find_reusable_embedding_bundle(
            project_id=_PROJECT_A,
            source_chunk_bundle_id="cb_01",
            embedding_profile_id=_PROFILE,
            configuration_fingerprint=_CONFIG_FP,
            expected_dimension=1024,
            expected_metric="cosine",
        )
        is None
    )


def test_falla_cerrado_cuando_dimension_o_metrica_no_revalida() -> None:
    policy, repo = _policy()
    repo.register_sealed(
        _bundle(_PROJECT_A),
        embedding_profile_id=_PROFILE,
        configuration_fingerprint=_CONFIG_FP,
    )

    with pytest.raises(MaterializationValidationFailed):
        policy.find_reusable_embedding_bundle(
            project_id=_PROJECT_A,
            source_chunk_bundle_id="cb_01",
            embedding_profile_id=_PROFILE,
            configuration_fingerprint=_CONFIG_FP,
            expected_dimension=768,
            expected_metric="cosine",
        )
