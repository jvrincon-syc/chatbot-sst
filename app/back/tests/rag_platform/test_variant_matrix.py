"""Fase 7 (Task 4): matriz de variantes construibles con versión en la identidad.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite; se ejecuta en la
máquina de gates reales.

Cubre:
- cada celda expone ``buildable`` y ``blocked_reason``,
- ``cell_id`` codifica IDs persistidos + ``configuration_version``,
- ``get_cell`` reconfirma contra la configuración vigente (fail-closed),
- un ``cell_id`` malformado se rechaza (``InvalidVariantMatrixCell``).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.variant_matrix_service import GetVariantMatrixUseCase
from rag_platform.domain.errors import (
    InvalidVariantMatrixCell,
    StaleVariantMatrixCell,
)
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
)

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_demo")
_EMBEDDING = "local-bge-m3-v1"
_ACTOR = PlatformActor(actor_id="op", project_scope=("proj_demo",))


def _configuration(*, version: int, embedding_enabled: bool = True) -> ProjectConfiguration:
    return ProjectConfiguration(
        version=version,
        embedding_profiles=(
            ProjectEmbeddingProfile(
                embedding_profile_id=_EMBEDDING, enabled=embedding_enabled
            ),
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


def _project(configuration: ProjectConfiguration) -> RagProject:
    roots = ProjectStorageRoots(
        project_id=_PROJECT,
        raw="data/projects/demo/raw",
        normalized="data/projects/demo/normalized",
        chunks="data/projects/demo/chunks",
        embeddings="data/projects/demo/embeddings",
        manifests="data/projects/demo/manifests",
    )
    return RagProject(
        project_id=_PROJECT,
        display_name="Demo",
        state=ProjectLifecycleState.ACTIVE,
        storage_roots=roots,
        configuration=configuration,
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


def _matrix(*, version: int, embedding_enabled: bool = True) -> GetVariantMatrixUseCase:
    projects = InMemoryProjectRepository()
    projects.add(_project(_configuration(version=version, embedding_enabled=embedding_enabled)))
    return GetVariantMatrixUseCase(
        projects=projects,
        processing_profiles=InMemoryProcessingProfileRepository((_processing(),)),
        chunking_profiles=InMemoryChunkingProfileRepository((_chunking(),)),
        access_policy=AllowAllAccessPolicy(),
    )


def test_variant_matrix_expone_buildable_y_blocked_reason_cuando_hay_config() -> None:
    cells = _matrix(version=3).execute(project_id=_PROJECT, actor=_ACTOR)

    assert len(cells) == 1
    cell = cells[0]
    assert cell.buildable is True
    assert cell.blocked_reason is None
    assert cell.configuration_version == 3
    assert cell.cell_id == "pp_local|cp_structural|local-bge-m3-v1|primary|3"


def test_variant_matrix_marca_no_buildable_cuando_embedding_deshabilitado() -> None:
    cells = _matrix(version=3, embedding_enabled=False).execute(
        project_id=_PROJECT, actor=_ACTOR
    )

    assert cells[0].buildable is False
    assert cells[0].blocked_reason == "embedding_profile_not_enabled"


def test_get_cell_reconfirma_celda_vigente() -> None:
    matrix = _matrix(version=3)

    cell = matrix.get_cell(
        project_id=_PROJECT,
        cell_id="pp_local|cp_structural|local-bge-m3-v1|primary|3",
        actor=_ACTOR,
    )

    assert cell.configuration_version == 3
    assert cell.embedding_profile_id == _EMBEDDING


def test_get_cell_de_version_obsoleta_falla_cerrado() -> None:
    # La configuración vigente es la 4; una celda pinneada a la 3 ya no aparece.
    matrix = _matrix(version=4)

    with pytest.raises(StaleVariantMatrixCell):
        matrix.get_cell(
            project_id=_PROJECT,
            cell_id="pp_local|cp_structural|local-bge-m3-v1|primary|3",
            actor=_ACTOR,
        )


def test_get_cell_malformado_falla_cerrado() -> None:
    matrix = _matrix(version=3)

    with pytest.raises(InvalidVariantMatrixCell):
        matrix.get_cell(
            project_id=_PROJECT, cell_id="pp_local|cp_structural", actor=_ACTOR
        )
