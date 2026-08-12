"""Task 4: orquestador que registra ``raw`` por proyecto sin tocar el legacy.

``RegisterProjectRawArtifactUseCase`` compone (no reimplementa): crea/reutiliza
la revisión lógica vía ``CreateSourceDocumentRevisionUseCase`` y persiste el
sidecar físico en el catálogo ``project_raw_document_artifacts``. La ruta física
se deriva de la raíz declarada del proyecto (``storage_roots.raw``), de modo que
el drift ``raw``/``docs_raw`` sea catalog-driven y no una constante.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.document_revision_service import (
    CreateSourceDocumentRevisionUseCase,
)
from rag_platform.application.raw_ingestion_service import (
    RegisterProjectRawArtifactRequest,
    RegisterProjectRawArtifactUseCase,
)
from rag_platform.domain.artifact_catalog import RawDocumentArtifactRecord
from rag_platform.domain.errors import ProjectNotFound
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    ProjectConfiguration,
    ProjectStorageRoots,
    RagProject,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryProjectRepository,
    InMemorySourceDocumentRepository,
)

_HASH = "d" * 64


class _FakeRawCatalog:
    """Catálogo físico raw en memoria, idempotente por revisión inmutable."""

    def __init__(self) -> None:
        self.rows: dict[str, RawDocumentArtifactRecord] = {}
        self.upserts = 0

    def upsert(
        self, record: RawDocumentArtifactRecord
    ) -> RawDocumentArtifactRecord:
        self.upserts += 1
        self.rows[record.source_document_revision_id] = record
        return record


def _project(*, raw_root: str = "projects/sst-general/docs_raw") -> RagProject:
    pid = PlatformId(kind=IdentityKind.PROJECT, value="proj_sst-general")
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    return RagProject(
        project_id=pid,
        display_name="SST General",
        storage_roots=ProjectStorageRoots(
            project_id=pid,
            raw=raw_root,
            normalized="projects/sst-general/normalized",
            chunks="projects/sst-general/chunks",
            embeddings="projects/sst-general/embeddings",
            manifests="projects/sst-general/manifests",
        ),
        configuration=ProjectConfiguration(
            version=1,
            corpus_organization_policy=CorpusOrganizationPolicy.SST_LEGACY_V1,
            created_at=now,
        ),
        created_at=now,
    )


def _service(
    *, project: RagProject | None = None
) -> tuple[RegisterProjectRawArtifactUseCase, _FakeRawCatalog]:
    projects = InMemoryProjectRepository()
    if project is not None:
        projects.add(project)
    revisions = CreateSourceDocumentRevisionUseCase(
        documents=InMemorySourceDocumentRepository(),
        access_policy=AllowAllAccessPolicy(),
    )
    raw_catalog = _FakeRawCatalog()
    service = RegisterProjectRawArtifactUseCase(
        projects=projects,
        revisions=revisions,
        raw_catalog=raw_catalog,
    )
    return service, raw_catalog


def _request() -> RegisterProjectRawArtifactRequest:
    return RegisterProjectRawArtifactRequest(
        project_id="sst-general",
        source_relpath="general/manual.pdf",
        raw_content_hash=_HASH,
        file_size=128,
    )


def test_registra_revision_y_catalogo_cuando_raw_es_valido() -> None:
    service, raw_catalog = _service(project=_project())

    revision = service.execute(_request(), actor_id="operator")

    assert revision.project_id.value == "proj_sst-general"
    stored = raw_catalog.rows[revision.source_document_revision_id.value]
    # La ruta física honra la raíz declarada del catálogo (docs_raw legacy).
    assert stored.artifact_relpath.endswith("docs_raw/general/manual.pdf")
    assert stored.source_relpath == "general/manual.pdf"
    assert stored.raw_content_hash == _HASH
    assert stored.uploaded_by == "operator"
    # Provenance de variante nunca es identidad del raw.
    assert not hasattr(stored, "rag_variant_id")


def test_deriva_ruta_desde_raiz_raw_cuando_proyecto_usa_layout_canonico() -> None:
    service, raw_catalog = _service(project=_project(raw_root="projects/sst-general/raw"))

    revision = service.execute(_request(), actor_id="operator")

    stored = raw_catalog.rows[revision.source_document_revision_id.value]
    assert stored.artifact_relpath == "projects/sst-general/raw/general/manual.pdf"


def test_reusa_revision_y_no_duplica_cuando_mismo_raw() -> None:
    service, raw_catalog = _service(project=_project())

    first = service.execute(_request(), actor_id="operator")
    again = service.execute(_request(), actor_id="otro-operador")

    assert first.source_document_revision_id == again.source_document_revision_id
    # La revisión inmutable conserva el actor original.
    assert again.uploaded_by == "operator"
    # El catálogo queda ligado a una sola fila por revisión.
    assert len(raw_catalog.rows) == 1


def test_falla_cerrado_cuando_proyecto_no_existe() -> None:
    service, _ = _service(project=None)

    with pytest.raises(ProjectNotFound):
        service.execute(_request(), actor_id="operator")
