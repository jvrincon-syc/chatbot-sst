"""Task 3: superficie de lectura/metadatos de proyectos (Fase 7), in-memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_platform.application.project_query_service import (
    GetProjectUseCase,
    ListChunkingProfilesUseCase,
    ListProcessingProfilesUseCase,
    ListProjectsUseCase,
    UpdateProjectMetadataUseCase,
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
from rag_platform.domain.errors import PlatformAccessDenied, ProjectNotFound
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryChunkingProfileRepository,
    InMemoryProcessingProfileRepository,
    InMemoryProjectRepository,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


def _repo_with_projects(tmp_path: Path) -> InMemoryProjectRepository:
    projects = InMemoryProjectRepository()
    create = CreateProjectUseCase(
        projects=projects,
        storage_roots=ProjectStorageResolver(tmp_path / "data"),
        access_policy=AllowAllAccessPolicy(),
        binding_provisioner=TargetBindingProvisioner(
            targets=InMemoryIndexingTargetRepository()
        ),
    )
    create.execute(
        CreateProjectRequest(project_slug="sst-general", display_name="SST"),
        actor=PlatformActor(actor_id="op"),
    )
    create.execute(
        CreateProjectRequest(project_slug="calidad", display_name="Calidad"),
        actor=PlatformActor(actor_id="op"),
    )
    return projects


def _pid(slug: str) -> PlatformId:
    return PlatformId(IdentityKind.PROJECT, f"proj_{slug}")


def _global_actor() -> PlatformActor:
    return PlatformActor(actor_id="op")


def test_list_projects_devuelve_todo_el_catalogo(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    result = ListProjectsUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    ).execute(actor=_global_actor())
    slugs = {p.project_id.value for p in result}
    assert slugs == {"proj_sst-general", "proj_calidad"}


def test_list_projects_acota_al_scope_del_actor(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    use_case = ListProjectsUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    )
    scoped = use_case.execute(
        actor=PlatformActor(actor_id="op", project_scope=("proj_sst-general",))
    )
    assert {p.project_id.value for p in scoped} == {"proj_sst-general"}
    empty = use_case.execute(actor=PlatformActor(actor_id="op", project_scope=()))
    assert empty == ()


def test_get_project_lee_por_id(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    project = GetProjectUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    ).execute(_pid("sst-general"), actor=_global_actor())
    assert project.project_id.value == "proj_sst-general"


def test_get_project_fuera_de_scope_falla_cerrado(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    with pytest.raises(PlatformAccessDenied):
        GetProjectUseCase(
            projects=projects, access_policy=AllowAllAccessPolicy()
        ).execute(
            _pid("calidad"),
            actor=PlatformActor(actor_id="op", project_scope=("proj_sst-general",)),
        )


def test_get_project_falla_cerrado_si_no_existe(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    with pytest.raises(ProjectNotFound):
        GetProjectUseCase(
            projects=projects, access_policy=AllowAllAccessPolicy()
        ).execute(_pid("inexistente"), actor=_global_actor())


def test_update_project_metadata_cambia_solo_display_name(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    updated = UpdateProjectMetadataUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    ).execute(_pid("sst-general"), display_name="SST Renombrado", actor=PlatformActor(actor_id="op"))
    assert updated.display_name == "SST Renombrado"
    assert updated.project_id.value == "proj_sst-general"


def test_list_profiles_vacio_cuando_no_hay_perfiles(tmp_path: Path) -> None:
    assert (
        ListProcessingProfilesUseCase(
            processing_profiles=InMemoryProcessingProfileRepository()
        ).execute(_pid("sst-general"))
        == ()
    )
    assert (
        ListChunkingProfilesUseCase(
            chunking_profiles=InMemoryChunkingProfileRepository()
        ).execute(_pid("sst-general"))
        == ()
    )
