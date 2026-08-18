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
from rag_platform.domain.errors import ProjectNotFound
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
    )
    create.execute(
        CreateProjectRequest(project_slug="sst-general", display_name="SST"),
        actor_id="op",
    )
    create.execute(
        CreateProjectRequest(project_slug="calidad", display_name="Calidad"),
        actor_id="op",
    )
    return projects


def _pid(slug: str) -> PlatformId:
    return PlatformId(IdentityKind.PROJECT, f"proj_{slug}")


def test_list_projects_devuelve_todo_el_catalogo(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    result = ListProjectsUseCase(projects=projects).execute()
    slugs = {p.project_id.value for p in result}
    assert slugs == {"proj_sst-general", "proj_calidad"}


def test_get_project_lee_por_id(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    project = GetProjectUseCase(projects=projects).execute(_pid("sst-general"))
    assert project.project_id.value == "proj_sst-general"


def test_get_project_falla_cerrado_si_no_existe(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    with pytest.raises(ProjectNotFound):
        GetProjectUseCase(projects=projects).execute(_pid("inexistente"))


def test_update_project_metadata_cambia_solo_display_name(tmp_path: Path) -> None:
    projects = _repo_with_projects(tmp_path)
    updated = UpdateProjectMetadataUseCase(
        projects=projects, access_policy=AllowAllAccessPolicy()
    ).execute(_pid("sst-general"), display_name="SST Renombrado", actor_id="op")
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
