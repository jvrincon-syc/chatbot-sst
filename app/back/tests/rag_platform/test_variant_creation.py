"""Fase 7 (Task 4): creación de variante desde una celda de matriz reconfirmada.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

Cubre:
- crear reconfirma la celda vigente y usa su ``configuration_version`` explícita,
- una celda obsoleta (config avanzó) falla cerrado (``StaleVariantMatrixCell``),
- el ``platform_id_body`` no duplica prefijos (``proj_proj_...``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.recipe_service import CreateRagVariantUseCase
from rag_platform.application.variant_matrix_service import (
    CreateRagVariantFromMatrixCellUseCase,
    GetVariantMatrixUseCase,
)
from rag_platform.domain.errors import StaleVariantMatrixCell
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    CorpusOrganizationPolicy,
    DocumentProcessingProfile,
    ProcessingOrigin,
    ProfileVerificationStatus,
    ProjectConfiguration,
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
    ProjectLifecycleState,
    ProjectStorageRoots,
    RagProject,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryChunkingProfileRepository,
    InMemoryProcessingProfileRepository,
    InMemoryProjectRepository,
    InMemoryRagVariantRepository,
    InMemoryTargetBindingResolver,
)

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_demo")
_EMBEDDING = "local-bge-m3-v1"
_CELL = "pp_local|cp_structural|local-bge-m3-v1|primary|3"


class _FakeEmbeddingProfiles:
    def get(self, profile_id: str) -> object:
        return SimpleNamespace(
            expected_fingerprint=lambda: SimpleNamespace(value="c" * 64)
        )


def _configuration(*, version: int) -> ProjectConfiguration:
    return ProjectConfiguration(
        version=version,
        embedding_profiles=(
            ProjectEmbeddingProfile(embedding_profile_id=_EMBEDDING, enabled=True),
        ),
        target_bindings=(
            ProjectIndexingTargetBinding(
                binding_key="primary",
                indexing_target_id="idx_vec_old",
                embedding_profile_id=_EMBEDDING,
            ),
        ),
        corpus_organization_policy=CorpusOrganizationPolicy.SOURCE_FOLDERS_V1,
        created_at=_NOW,
    )


def _project() -> RagProject:
    return RagProject(
        project_id=_PROJECT,
        display_name="Demo",
        state=ProjectLifecycleState.ACTIVE,
        storage_roots=ProjectStorageRoots(
            project_id=_PROJECT,
            raw="data/projects/demo/raw",
            normalized="data/projects/demo/normalized",
            chunks="data/projects/demo/chunks",
            embeddings="data/projects/demo/embeddings",
            manifests="data/projects/demo/manifests",
        ),
        configuration=_configuration(version=3),
        created_at=_NOW,
    )


def _processing() -> DocumentProcessingProfile:
    return DocumentProcessingProfile(
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local"),
        project_id=_PROJECT,
        provider="local",
        engine="pdf-ocr-v1",
        observed_revision="rev-1",
        origin=ProcessingOrigin.LOCAL,
        sanitized_config={},
        fingerprint="a" * 64,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=_NOW,
    )


def _chunking() -> ChunkingProfile:
    return ChunkingProfile(
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_structural"),
        project_id=_PROJECT,
        strategy="structural",
        sanitized_config={},
        fingerprint="b" * 64,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=_NOW,
    )


def _build() -> tuple[
    CreateRagVariantFromMatrixCellUseCase, InMemoryProjectRepository
]:
    projects = InMemoryProjectRepository()
    projects.add(_project())
    processing = InMemoryProcessingProfileRepository((_processing(),))
    chunking = InMemoryChunkingProfileRepository((_chunking(),))
    matrix = GetVariantMatrixUseCase(
        projects=projects,
        processing_profiles=processing,
        chunking_profiles=chunking,
    )
    create_variant = CreateRagVariantUseCase(
        variants=InMemoryRagVariantRepository(),
        processing_profiles=processing,
        chunking_profiles=chunking,
        embedding_profiles=_FakeEmbeddingProfiles(),
        target_bindings=InMemoryTargetBindingResolver(
            (
                ProjectIndexingTargetBinding(
                    binding_key="primary",
                    indexing_target_id="idx_vec_old",
                    embedding_profile_id=_EMBEDDING,
                ),
            ),
            configuration_version=3,
        ),
        access_policy=AllowAllAccessPolicy(),
    )
    use_case = CreateRagVariantFromMatrixCellUseCase(
        matrix=matrix, create_variant=create_variant
    )
    return use_case, projects


def _actor() -> PlatformActor:
    return PlatformActor(actor_id="op-1", project_scope=("proj_demo",))


def test_create_variant_from_matrix_cell_reconfirma_celda_vigente() -> None:
    use_case, _ = _build()

    variant = use_case.execute(
        project_id=_PROJECT,
        cell_id=_CELL,
        variant_slug="sst-local-bge-m3-v2",
        actor=_actor(),
    )

    assert variant.embedding_profile_id == _EMBEDDING


def test_create_variant_from_stale_matrix_cell_falla_cerrado() -> None:
    use_case, projects = _build()
    # La configuración avanza a la v4 entre el GET de la matriz y el POST.
    projects.create_version(_PROJECT, _configuration(version=4))

    with pytest.raises(StaleVariantMatrixCell):
        use_case.execute(
            project_id=_PROJECT,
            cell_id=_CELL,
            variant_slug="sst-local-bge-m3-v2",
            actor=_actor(),
        )


def test_create_variant_from_matrix_cell_no_duplica_prefijos() -> None:
    use_case, _ = _build()

    variant = use_case.execute(
        project_id=_PROJECT,
        cell_id=_CELL,
        variant_slug="sst-local-bge-m3-v2",
        actor=_actor(),
    )

    assert variant.project_id.value == "proj_demo"
    assert variant.processing_profile_id.value == "pp_local"
    assert variant.chunking_profile_id.value == "cp_structural"
    assert variant.embedding_profile_id == "local-bge-m3-v1"
