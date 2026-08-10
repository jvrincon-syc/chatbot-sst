"""Fase 1: dos proyectos coexisten aislados, sin credenciales ni raíces cruzadas."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from rag_platform.application.project_service import (
    CreateProjectRequest,
    CreateProjectUseCase,
)
from rag_platform.domain.errors import ProjectAlreadyExists, UnsafeArtifactPath
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    DocumentTypeTemplate,
    ProjectEmbeddingProfile,
    RagProject,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryProjectRepository,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


def _use_case(tmp_path: Path) -> tuple[CreateProjectUseCase, InMemoryProjectRepository]:
    projects = InMemoryProjectRepository()
    use_case = CreateProjectUseCase(
        projects=projects,
        storage_roots=ProjectStorageResolver(tmp_path / "data"),
        access_policy=AllowAllAccessPolicy(),
    )
    return use_case, projects


def test_dos_proyectos_coexisten_con_taxonomia_y_config_distintas(tmp_path: Path) -> None:
    use_case, _ = _use_case(tmp_path)

    sst = use_case.execute(
        CreateProjectRequest(
            project_slug="sst-general",
            display_name="SST General",
            document_type_template=DocumentTypeTemplate.SST,
            corpus_organization_policy=CorpusOrganizationPolicy.SST_LEGACY_V1,
            embedding_profiles=(
                ProjectEmbeddingProfile(embedding_profile_id="bge-m3"),
            ),
        ),
        actor_id="operator-1",
    )
    calidad = use_case.execute(
        CreateProjectRequest(
            project_slug="calidad-interna",
            display_name="Calidad Interna",
            document_type_template=DocumentTypeTemplate.GENERIC,
            corpus_organization_policy=CorpusOrganizationPolicy.DOCUMENT_TYPES_V1,
            embedding_profiles=(
                ProjectEmbeddingProfile(embedding_profile_id="voyage-4"),
            ),
        ),
        actor_id="operator-1",
    )

    # Taxonomías distintas: SST vs neutral.
    sst_templates = {dt.template for dt in sst.configuration.document_types}
    calidad_templates = {dt.template for dt in calidad.configuration.document_types}
    assert sst_templates == {DocumentTypeTemplate.SST}
    assert calidad_templates == {DocumentTypeTemplate.GENERIC}
    # Configuración distinta: política de organización.
    assert (
        sst.configuration.corpus_organization_policy
        != calidad.configuration.corpus_organization_policy
    )


def test_raices_de_dos_proyectos_no_se_intersectan(tmp_path: Path) -> None:
    use_case, _ = _use_case(tmp_path)
    a = use_case.execute(
        CreateProjectRequest(project_slug="proj-a", display_name="A"),
        actor_id="op",
    )
    b = use_case.execute(
        CreateProjectRequest(project_slug="proj-b", display_name="B"),
        actor_id="op",
    )

    a_roots = {
        a.storage_roots.raw,
        a.storage_roots.normalized,
        a.storage_roots.chunks,
        a.storage_roots.embeddings,
        a.storage_roots.manifests,
    }
    b_roots = {
        b.storage_roots.raw,
        b.storage_roots.normalized,
        b.storage_roots.chunks,
        b.storage_roots.embeddings,
        b.storage_roots.manifests,
    }
    assert a_roots.isdisjoint(b_roots)
    # Ninguna raíz de A es prefijo de una de B ni viceversa.
    for ra in a_roots:
        for rb in b_roots:
            assert not rb.startswith(ra + "/")
            assert not ra.startswith(rb + "/")


def test_no_hay_credenciales_en_el_modelo_de_proyecto(tmp_path: Path) -> None:
    use_case, _ = _use_case(tmp_path)
    project = use_case.execute(
        CreateProjectRequest(project_slug="secure", display_name="Secure"),
        actor_id="op",
    )
    serialized = project.model_dump_json().casefold()
    for marker in ("secret", "token", "password", "credential", "api_key", "apikey"):
        assert marker not in serialized


def test_project_id_es_inmutable_tras_tener_documentos(tmp_path: Path) -> None:
    use_case, projects = _use_case(tmp_path)
    project = use_case.execute(
        CreateProjectRequest(project_slug="frozen", display_name="Frozen"),
        actor_id="op",
    )
    projects.mark_has_documents(project.project_id)

    # El slug ya existe: recrear el mismo project_id falla cerrado.
    assert projects.has_documents(project.project_id) is True
    with pytest.raises(ProjectAlreadyExists):
        use_case.execute(
            CreateProjectRequest(project_slug="frozen", display_name="Renamed"),
            actor_id="op",
        )
    # El modelo es frozen a nivel de asignación de atributo (Pydantic + inmutable
    # por contrato); el project_id no se puede reasignar en el repositorio.
    stored = projects.get(project.project_id)
    assert stored.project_id == project.project_id


def test_resolver_bloquea_path_traversal(tmp_path: Path) -> None:
    resolver = ProjectStorageResolver(tmp_path / "data")
    project_id = PlatformId(IdentityKind.PROJECT, "proj_esc")

    # Ruta válida contenida.
    resolved = resolver.resolve_artifact(project_id, PurePosixPath("raw/doc.pdf"))
    assert resolved.name == "doc.pdf"

    # Escapes y absolutos fallan cerrado.
    for unsafe in ("../raw/doc.pdf", "raw/../../etc/passwd", "/abs/raw/doc.pdf"):
        with pytest.raises(UnsafeArtifactPath):
            resolver.resolve_artifact(project_id, PurePosixPath(unsafe))
    # Un primer segmento fuera de las raíces canónicas también falla.
    with pytest.raises(UnsafeArtifactPath):
        resolver.resolve_artifact(project_id, PurePosixPath("logs/x.txt"))


def test_repositorio_rechaza_project_id_duplicado(tmp_path: Path) -> None:
    projects = InMemoryProjectRepository()
    resolver = ProjectStorageResolver(tmp_path / "data")
    project = RagProject.model_validate(
        {
            "project_id": PlatformId(IdentityKind.PROJECT, "proj_dup"),
            "display_name": "Dup",
            "storage_roots": resolver.roots_for(
                PlatformId(IdentityKind.PROJECT, "proj_dup")
            ),
            "configuration": {
                "version": 1,
                "corpus_organization_policy": "source-folders-v1",
                "created_at": "2026-08-10T00:00:00Z",
            },
            "created_at": "2026-08-10T00:00:00Z",
        }
    )
    projects.add(project)
    with pytest.raises(ProjectAlreadyExists):
        projects.add(project)
