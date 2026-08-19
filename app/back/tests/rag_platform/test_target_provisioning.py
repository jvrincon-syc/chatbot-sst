"""Fase 7 (Task 2): provisioning server-side de target bindings.

PENDIENTE DE EJECUCIÓN por el operador.

Cubre:
- el provisioner deriva un binding por perfil de embedding con target compatible;
- perfiles sin target compatible o deshabilitados no fabrican binding (fail-closed);
- ``CreateProjectUseCase`` provisiona bindings desde el catálogo global cuando el
  request HTTP no trae bindings (nunca expone ``indexing_target_id``);
- un request con bindings explícitos (seed/admin de confianza) los respeta;
- tras provisionar, la matriz de variantes tiene una celda construible;
- el binding físico nunca proviene del cliente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rag_platform.application.project_service import (
    CreateProjectRequest,
    CreateProjectUseCase,
)
from rag_platform.application.target_provisioning import TargetBindingProvisioner
from rag_platform.application.variant_matrix_service import GetVariantMatrixUseCase
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    DocumentProcessingProfile,
    ProcessingOrigin,
    ProfileVerificationStatus,
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryChunkingProfileRepository,
    InMemoryProcessingProfileRepository,
    InMemoryProjectRepository,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver

_NOW = datetime(2026, 8, 19, tzinfo=timezone.utc)
_EMBED = "local-bge-m3-v1"
_PID = PlatformId(IdentityKind.PROJECT, "proj_demo")


@dataclass(frozen=True)
class _Target:
    indexing_target_id: str
    embedding_profile_id: str | None


class _Catalog:
    def __init__(self, targets: tuple[_Target, ...]) -> None:
        self._targets = targets

    def list_targets(self) -> tuple[_Target, ...]:
        return self._targets


def _profile(embedding_profile_id: str = _EMBED, *, enabled: bool = True):
    return ProjectEmbeddingProfile(
        embedding_profile_id=embedding_profile_id, enabled=enabled
    )


# --------------------------------------------------------------------------- #
# Provisioner                                                                  #
# --------------------------------------------------------------------------- #


def test_provisiona_binding_para_perfil_con_target_compatible() -> None:
    catalog = _Catalog(
        (
            _Target("idx_vec_local_bge_m3_v1", _EMBED),
            _Target("idx_vec_voyage", "voyage-4"),
        )
    )
    bindings = TargetBindingProvisioner(targets=catalog).provision((_profile(),))
    assert len(bindings) == 1
    assert bindings[0].binding_key == _EMBED
    assert bindings[0].embedding_profile_id == _EMBED
    assert bindings[0].indexing_target_id == "idx_vec_local_bge_m3_v1"


def test_no_provisiona_sin_target_compatible_fail_closed() -> None:
    catalog = _Catalog((_Target("idx_vec_voyage", "voyage-4"),))
    assert TargetBindingProvisioner(targets=catalog).provision((_profile(),)) == ()


def test_no_provisiona_para_perfil_deshabilitado() -> None:
    catalog = _Catalog((_Target("idx_vec_local_bge_m3_v1", _EMBED),))
    assert (
        TargetBindingProvisioner(targets=catalog).provision(
            (_profile(enabled=False),)
        )
        == ()
    )


def test_target_compatible_es_determinista_menor_id() -> None:
    catalog = _Catalog(
        (
            _Target("idx_vec_b", _EMBED),
            _Target("idx_vec_a", _EMBED),
        )
    )
    bindings = TargetBindingProvisioner(targets=catalog).provision((_profile(),))
    assert bindings[0].indexing_target_id == "idx_vec_a"


# --------------------------------------------------------------------------- #
# CreateProjectUseCase provisioning                                            #
# --------------------------------------------------------------------------- #


def _create_use_case(
    tmp_path: Path, catalog: _Catalog
) -> tuple[CreateProjectUseCase, InMemoryProjectRepository]:
    projects = InMemoryProjectRepository()
    use_case = CreateProjectUseCase(
        projects=projects,
        storage_roots=ProjectStorageResolver(tmp_path / "data"),
        access_policy=AllowAllAccessPolicy(),
        binding_provisioner=TargetBindingProvisioner(targets=catalog),
    )
    return use_case, projects


def test_create_project_provisiona_bindings_desde_el_catalogo(tmp_path: Path) -> None:
    catalog = _Catalog((_Target("idx_vec_local_bge_m3_v1", _EMBED),))
    use_case, _ = _create_use_case(tmp_path, catalog)
    project = use_case.execute(
        CreateProjectRequest(
            project_slug="demo",
            display_name="Demo",
            embedding_profiles=(_profile(),),
        ),
        actor=PlatformActor(actor_id="op"),
    )
    bindings = project.configuration.target_bindings
    assert len(bindings) == 1
    assert bindings[0].indexing_target_id == "idx_vec_local_bge_m3_v1"
    assert bindings[0].embedding_profile_id == _EMBED


def test_create_project_respeta_bindings_explicitos(tmp_path: Path) -> None:
    # Un catálogo con otro target no debe usarse cuando el request trae bindings.
    catalog = _Catalog((_Target("idx_vec_provisioned", _EMBED),))
    use_case, _ = _create_use_case(tmp_path, catalog)
    explicit = ProjectIndexingTargetBinding(
        binding_key="primary",
        indexing_target_id="idx_vec_explicit",
        embedding_profile_id=_EMBED,
    )
    project = use_case.execute(
        CreateProjectRequest(
            project_slug="demo",
            display_name="Demo",
            embedding_profiles=(_profile(),),
            target_bindings=(explicit,),
        ),
        actor=PlatformActor(actor_id="op"),
    )
    assert project.configuration.target_bindings == (explicit,)


def test_matriz_es_construible_tras_provisionar(tmp_path: Path) -> None:
    catalog = _Catalog((_Target("idx_vec_local_bge_m3_v1", _EMBED),))
    use_case, projects = _create_use_case(tmp_path, catalog)
    use_case.execute(
        CreateProjectRequest(
            project_slug="demo",
            display_name="Demo",
            embedding_profiles=(_profile(),),
        ),
        actor=PlatformActor(actor_id="op"),
    )
    matrix = GetVariantMatrixUseCase(
        projects=projects,
        processing_profiles=InMemoryProcessingProfileRepository((_processing(),)),
        chunking_profiles=InMemoryChunkingProfileRepository((_chunking(),)),
        access_policy=AllowAllAccessPolicy(),
    )
    cells = matrix.execute(project_id=_PID, actor=PlatformActor(actor_id="op"))
    buildable = [c for c in cells if c.buildable]
    assert len(buildable) == 1
    assert buildable[0].embedding_profile_id == _EMBED
    assert buildable[0].target_binding_key == _EMBED


def _processing() -> DocumentProcessingProfile:
    return DocumentProcessingProfile(
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local"),
        project_id=_PID,
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
        project_id=_PID,
        strategy="structural",
        sanitized_config={},
        fingerprint="b" * 64,
        status=ProfileVerificationStatus.VERIFIED,
        created_at=_NOW,
    )
