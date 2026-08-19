"""Task 3: configuración versionada por proyecto (lectura vigente/histórica + nueva versión).

La historia no se colapsa en la última versión: leer la versión 1 tras crear la 2
sigue devolviendo sus ``target_bindings`` originales (in-memory, sin Postgres).
"""

from __future__ import annotations

from pathlib import Path

from rag_platform.application.project_configuration_service import (
    CreateProjectConfigurationVersionUseCase,
    GetProjectConfigurationUseCase,
    GetProjectConfigurationVersionUseCase,
    UpdateProjectConfigurationRequest,
)
from rag_platform.application.project_service import (
    CreateProjectRequest,
    CreateProjectUseCase,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.target_provisioning import TargetBindingProvisioner
from embedding.infrastructure.in_memory.repositories import (
    InMemoryIndexingTargetRepository,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    ProjectIndexingTargetBinding,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryProjectRepository,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


def _pid() -> PlatformId:
    return PlatformId(IdentityKind.PROJECT, "proj_sst-general")


def _seed(tmp_path: Path) -> InMemoryProjectRepository:
    projects = InMemoryProjectRepository()
    CreateProjectUseCase(
        projects=projects,
        storage_roots=ProjectStorageResolver(tmp_path / "data"),
        access_policy=AllowAllAccessPolicy(),
        binding_provisioner=TargetBindingProvisioner(
            targets=InMemoryIndexingTargetRepository()
        ),
    ).execute(
        CreateProjectRequest(project_slug="sst-general", display_name="SST"),
        actor=PlatformActor(actor_id="op"),
    )
    return projects


def test_get_configuration_vigente_es_la_ultima_version(tmp_path: Path) -> None:
    projects = _seed(tmp_path)
    config = GetProjectConfigurationUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    ).execute(_pid(), actor=PlatformActor(actor_id="op"))
    assert config.version == 1


def test_create_version_incrementa_monotona_y_preserva_historia(tmp_path: Path) -> None:
    projects = _seed(tmp_path)
    new = CreateProjectConfigurationVersionUseCase(
        projects=projects,
        configurations=projects,
        access_policy=AllowAllAccessPolicy(),
    ).execute(
        _pid(),
        request=UpdateProjectConfigurationRequest(
            corpus_organization_policy=CorpusOrganizationPolicy.SOURCE_FOLDERS_V1,
            target_bindings=(
                ProjectIndexingTargetBinding(
                    binding_key="default",
                    indexing_target_id="idx_vec_local_bge_m3_v1",
                    embedding_profile_id="bge-m3",
                ),
            ),
        ),
        actor=PlatformActor(actor_id="op"),
    )
    assert new.version == 2

    # La versión 1 histórica NO se colapsa: sigue sin el binding nuevo.
    v1 = GetProjectConfigurationVersionUseCase(configurations=projects).execute(
        _pid(), version=1
    )
    assert v1.version == 1
    assert v1.target_bindings == ()

    v2 = GetProjectConfigurationVersionUseCase(configurations=projects).execute(
        _pid(), version=2
    )
    assert {binding.binding_key for binding in v2.target_bindings} == {"default"}


def _seed_with_binding(tmp_path: Path) -> InMemoryProjectRepository:
    """Siembra un proyecto cuya v1 ya tiene un binding server-controlled."""

    projects = InMemoryProjectRepository()
    CreateProjectUseCase(
        projects=projects,
        storage_roots=ProjectStorageResolver(tmp_path / "data"),
        access_policy=AllowAllAccessPolicy(),
        binding_provisioner=TargetBindingProvisioner(
            targets=InMemoryIndexingTargetRepository()
        ),
    ).execute(
        CreateProjectRequest(
            project_slug="sst-general",
            display_name="SST",
            target_bindings=(
                ProjectIndexingTargetBinding(
                    binding_key="primary",
                    indexing_target_id="idx_vec_local_bge_m3_v1",
                    embedding_profile_id="bge-m3",
                ),
            ),
        ),
        actor=PlatformActor(actor_id="op"),
    )
    return projects


def test_patch_sin_bindings_preserva_los_server_controlled(tmp_path: Path) -> None:
    # El DTO HTTP omite target_bindings → None → preservar (nunca borrar).
    projects = _seed_with_binding(tmp_path)
    v2 = CreateProjectConfigurationVersionUseCase(
        projects=projects,
        configurations=projects,
        access_policy=AllowAllAccessPolicy(),
    ).execute(
        _pid(),
        request=UpdateProjectConfigurationRequest(
            corpus_organization_policy=CorpusOrganizationPolicy.SOURCE_FOLDERS_V1,
            # target_bindings omitido = None = preservar.
        ),
        actor=PlatformActor(actor_id="op"),
    )
    assert v2.version == 2
    assert {b.binding_key for b in v2.target_bindings} == {"primary"}
    assert v2.target_bindings[0].indexing_target_id == "idx_vec_local_bge_m3_v1"

    # La v1 histórica sigue intacta.
    v1 = GetProjectConfigurationVersionUseCase(configurations=projects).execute(
        _pid(), version=1
    )
    assert {b.binding_key for b in v1.target_bindings} == {"primary"}
