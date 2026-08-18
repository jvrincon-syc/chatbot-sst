"""Fase 1: identidad de receta semántica y bloqueos fail-closed de variante."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.recipe_service import (
    CreateRagVariantRequest,
    CreateRagVariantUseCase,
)
from rag_platform.domain.errors import (
    DuplicateVariantRecipe,
    IncompatibleTargetBinding,
    UnverifiableRecipeRevision,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    DocumentProcessingProfile,
    ProcessingOrigin,
    ProfileVerificationStatus,
    ProjectIndexingTargetBinding,
    compute_semantic_recipe_fingerprint,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryChunkingProfileRepository,
    InMemoryProcessingProfileRepository,
    InMemoryRagVariantRepository,
    InMemoryTargetBindingResolver,
)


_PROJECT = "sst-general"
_EMBEDDING_FP = "c" * 64


class _FakeEmbeddingProfile:
    """Perfil de embedding fake con un fingerprint de config fijo."""

    def __init__(self, fingerprint: str) -> None:
        self._fingerprint = fingerprint

    def expected_fingerprint(self) -> "object":
        from types import SimpleNamespace

        return SimpleNamespace(value=self._fingerprint)


class _FakeEmbeddingProfiles:
    """Lector de perfiles de embedding en memoria para las pruebas de receta."""

    def __init__(self, fingerprint: str = _EMBEDDING_FP) -> None:
        self._fingerprint = fingerprint

    def get(self, profile_id: str) -> _FakeEmbeddingProfile:
        return _FakeEmbeddingProfile(self._fingerprint)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _processing(
    *,
    config: dict | None = None,
    engine: str = "pdf-ocr-v1",
    status: ProfileVerificationStatus = ProfileVerificationStatus.VERIFIED,
) -> DocumentProcessingProfile:
    fp = compute_semantic_recipe_fingerprint(
        processing_provider="local",
        processing_engine=engine,
        processing_revision="rev-1",
        processing_config=config or {},
        chunking_strategy="structural-v1",
        chunking_config={},
        embedding_profile_id="bge-m3",
        embedding_configuration_fingerprint=_EMBEDDING_FP,
    )
    return DocumentProcessingProfile(
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local-v1"),
        project_id=PlatformId(IdentityKind.PROJECT, f"proj_{_PROJECT}"),
        provider="local",
        engine=engine,
        observed_revision="rev-1",
        origin=ProcessingOrigin.LOCAL,
        sanitized_config=config or {},
        fingerprint=fp[:64],
        status=status,
        created_at=_now(),
    )


def _chunking() -> ChunkingProfile:
    fp = compute_semantic_recipe_fingerprint(
        processing_provider="x",
        processing_engine="x",
        processing_revision="x",
        processing_config={},
        chunking_strategy="structural-v1",
        chunking_config={},
        embedding_profile_id="x",
        embedding_configuration_fingerprint=_EMBEDDING_FP,
    )
    return ChunkingProfile(
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_structural-v1"),
        project_id=PlatformId(IdentityKind.PROJECT, f"proj_{_PROJECT}"),
        strategy="structural-v1",
        sanitized_config={},
        fingerprint=fp,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=_now(),
    )


def _use_case(
    processing: DocumentProcessingProfile,
    *,
    variants: InMemoryRagVariantRepository | None = None,
    binding_embedding: str = "bge-m3",
) -> tuple[CreateRagVariantUseCase, InMemoryRagVariantRepository]:
    variants = variants or InMemoryRagVariantRepository()
    use_case = CreateRagVariantUseCase(
        variants=variants,
        processing_profiles=InMemoryProcessingProfileRepository((processing,)),
        chunking_profiles=InMemoryChunkingProfileRepository((_chunking(),)),
        embedding_profiles=_FakeEmbeddingProfiles(),
        target_bindings=InMemoryTargetBindingResolver(
            (
                ProjectIndexingTargetBinding(
                    binding_key="local-bge-primary",
                    indexing_target_id="tgt-local",
                    embedding_profile_id=binding_embedding,
                ),
            )
        ),
        access_policy=AllowAllAccessPolicy(),
    )
    return use_case, variants


def _request(**overrides: object) -> CreateRagVariantRequest:
    base = {
        "variant_slug": "local-bge-m3",
        "project_id": _PROJECT,
        "processing_profile_id": "local-v1",
        "chunking_profile_id": "structural-v1",
        "embedding_profile_id": "bge-m3",
        "target_binding_key": "local-bge-primary",
        "configuration_version": 1,
    }
    base.update(overrides)
    return CreateRagVariantRequest(**base)  # type: ignore[arg-type]


def test_misma_receta_produce_mismo_fingerprint_y_rechaza_duplicado() -> None:
    use_case, variants = _use_case(_processing())
    first = use_case.execute(_request(), actor_id="op")

    # Segunda variante con la misma receta => mismo fingerprint => rechazo.
    with pytest.raises(DuplicateVariantRecipe):
        use_case.execute(_request(variant_slug="local-bge-m3-dup"), actor_id="op")
    assert (
        variants.find_active_by_fingerprint(
            first.project_id, first.semantic_recipe_fingerprint
        )
        is not None
    )


def test_cambio_semantico_produce_fingerprint_distinto_y_variante_nueva() -> None:
    processing_a = _processing(engine="pdf-ocr-v1")
    use_case_a, variants = _use_case(processing_a)
    variant_a = use_case_a.execute(_request(), actor_id="op")

    # Cambio de motor (semántico) sobre el mismo repositorio de variantes.
    processing_b = _processing(engine="pdf-ocr-v2")
    use_case_b, _ = _use_case(processing_b, variants=variants)
    variant_b = use_case_b.execute(
        _request(variant_slug="local-bge-m3-v2"), actor_id="op"
    )

    assert (
        variant_a.semantic_recipe_fingerprint != variant_b.semantic_recipe_fingerprint
    )


def test_cambio_de_credencial_no_cambia_fingerprint() -> None:
    without_secret = compute_semantic_recipe_fingerprint(
        processing_provider="llama_cloud",
        processing_engine="llamaparse",
        processing_revision="2026-08",
        processing_config={"mode": "accurate"},
        chunking_strategy="structural-v1",
        chunking_config={},
        embedding_profile_id="bge-m3",
        embedding_configuration_fingerprint=_EMBEDDING_FP,
    )
    with_secret = compute_semantic_recipe_fingerprint(
        processing_provider="llama_cloud",
        processing_engine="llamaparse",
        processing_revision="2026-08",
        processing_config={"mode": "accurate", "api_key": "sk-XYZ", "token": "abc"},
        chunking_strategy="structural-v1",
        chunking_config={},
        embedding_profile_id="bge-m3",
        embedding_configuration_fingerprint=_EMBEDDING_FP,
    )
    assert without_secret == with_secret


def test_target_incompatible_bloquea_variante_fail_closed() -> None:
    # El binding declara un embedding distinto al de la variante.
    use_case, _ = _use_case(_processing(), binding_embedding="voyage-4")
    with pytest.raises(IncompatibleTargetBinding):
        use_case.execute(_request(embedding_profile_id="bge-m3"), actor_id="op")


def test_binding_desconocido_bloquea_variante_fail_closed() -> None:
    use_case, _ = _use_case(_processing())
    with pytest.raises(IncompatibleTargetBinding):
        use_case.execute(_request(target_binding_key="inexistente"), actor_id="op")


def test_revision_no_verificable_bloquea_sin_attestation() -> None:
    processing = _processing(status=ProfileVerificationStatus.UNVERIFIABLE)
    use_case, _ = _use_case(processing)

    with pytest.raises(UnverifiableRecipeRevision):
        use_case.execute(_request(), actor_id="op")

    # Con attestation explícita se permite.
    variant = use_case.execute(
        _request(allow_unverifiable_revision=True), actor_id="op"
    )
    assert variant.rag_variant_id.kind is IdentityKind.RAG_VARIANT
