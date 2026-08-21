from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.project_raw_upload_service import (
    UploadProjectRawDocumentUseCase,
)
from rag_platform.domain.errors import (
    PlatformAccessDenied,
    ProjectNotFound,
    UnsafeArtifactPath,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    ProjectConfiguration,
    ProjectStorageRoots,
    RagProject,
    RevisionReviewState,
    SourceDocumentRevision,
)
from rag_platform.infrastructure.in_memory.repositories import InMemoryProjectRepository


_NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class _AllowAll:
    def require_operator(self, *, actor_id: str) -> None:
        if not actor_id.strip():
            raise PlatformAccessDenied("empty actor")


class _DenyAll:
    def require_operator(self, *, actor_id: str) -> None:
        raise PlatformAccessDenied("denied")


class _RecordingStorage:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[RagProject, str, bytes]] = []

    def write_raw_bytes(
        self, project: RagProject, source_relpath: str, content: bytes
    ) -> None:
        self.calls.append((project, source_relpath, content))
        if self.error is not None:
            raise self.error


class _RecordingRegister:
    def __init__(
        self,
        *,
        result: SourceDocumentRevision | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or _revision()
        self.error = error
        self.calls: list[tuple[object, str]] = []

    def execute(self, request, *, actor_id: str) -> SourceDocumentRevision:
        self.calls.append((request, actor_id))
        if self.error is not None:
            raise self.error
        return self.result


def _project() -> RagProject:
    project_id = PlatformId(IdentityKind.PROJECT, "proj_sst-general")
    return RagProject(
        project_id=project_id,
        display_name="SST General",
        storage_roots=ProjectStorageRoots(
            project_id=project_id,
            raw="projects/sst-general/raw",
            normalized="projects/sst-general/normalized",
            chunks="projects/sst-general/chunks",
            embeddings="projects/sst-general/embeddings",
            manifests="projects/sst-general/manifests",
        ),
        configuration=ProjectConfiguration(
            version=1,
            corpus_organization_policy=CorpusOrganizationPolicy.SST_LEGACY_V1,
            created_at=_NOW,
        ),
        created_at=_NOW,
    )


def _revision() -> SourceDocumentRevision:
    return SourceDocumentRevision(
        source_document_revision_id=PlatformId(
            IdentityKind.SOURCE_DOCUMENT_REVISION, "srev_manual-001"
        ),
        logical_document_id=PlatformId(IdentityKind.SOURCE_DOCUMENT, "sdoc_manual"),
        project_id=PlatformId(IdentityKind.PROJECT, "proj_sst-general"),
        source_relpath="manuales/manual.pdf",
        raw_content_hash="a" * 64,
        file_size=42,
        uploaded_by="operator-1",
        uploaded_at=_NOW,
        review_state=RevisionReviewState.PROCESSED,
    )


def _use_case(
    *,
    project: RagProject | None = None,
    storage: _RecordingStorage | None = None,
    register: _RecordingRegister | None = None,
    policy=None,
) -> tuple[UploadProjectRawDocumentUseCase, _RecordingStorage, _RecordingRegister]:
    projects = InMemoryProjectRepository()
    if project is not None:
        projects.add(project)
    storage = storage or _RecordingStorage()
    register = register or _RecordingRegister()
    use_case = UploadProjectRawDocumentUseCase(
        projects=projects,
        storage=storage,
        register=register,
        access_policy=policy or _AllowAll(),
    )
    return use_case, storage, register


def test_upload_raw_calcula_hash_y_delega_storage_y_registro() -> None:
    project = _project()
    expected_revision = _revision()
    use_case, storage, register = _use_case(
        project=project,
        register=_RecordingRegister(result=expected_revision),
    )
    content = b"%PDF-1.4 contenido"

    revision = use_case.execute(
        project_id=project.project_id,
        source_relpath="manuales/manual.pdf",
        content=content,
        actor=PlatformActor(actor_id="operator-1"),
    )

    assert revision == expected_revision
    assert storage.calls == [(project, "manuales/manual.pdf", content)]
    request, actor_id = register.calls[0]
    assert request.project_id == "sst-general"
    assert request.source_relpath == "manuales/manual.pdf"
    assert request.raw_content_hash == sha256(content).hexdigest()
    assert request.file_size == len(content)
    assert actor_id == "operator-1"


def test_upload_raw_falla_cerrado_si_actor_esta_fuera_del_scope() -> None:
    project = _project()
    use_case, storage, register = _use_case(project=project)

    with pytest.raises(PlatformAccessDenied):
        use_case.execute(
            project_id=project.project_id,
            source_relpath="manuales/manual.pdf",
            content=b"pdf",
            actor=PlatformActor(
                actor_id="operator-1", project_scope=("proj_otro-proyecto",)
            ),
        )

    assert storage.calls == []
    assert register.calls == []


def test_upload_raw_falla_cerrado_si_el_proyecto_no_existe() -> None:
    use_case, storage, register = _use_case(project=None)

    with pytest.raises(ProjectNotFound):
        use_case.execute(
            project_id=PlatformId(IdentityKind.PROJECT, "proj_sst-general"),
            source_relpath="manuales/manual.pdf",
            content=b"pdf",
            actor=PlatformActor(actor_id="operator-1"),
        )

    assert storage.calls == []
    assert register.calls == []


def test_upload_raw_propagates_error_de_path_inseguro_sin_registrar() -> None:
    project = _project()
    use_case, storage, register = _use_case(
        project=project,
        storage=_RecordingStorage(error=UnsafeArtifactPath("traversal")),
    )

    with pytest.raises(UnsafeArtifactPath):
        use_case.execute(
            project_id=project.project_id,
            source_relpath="../manual.pdf",
            content=b"pdf",
            actor=PlatformActor(actor_id="operator-1"),
        )

    assert len(storage.calls) == 1
    assert register.calls == []


def test_upload_raw_no_oculta_fallo_de_registro_despues_de_escribir_bytes() -> None:
    project = _project()
    use_case, storage, register = _use_case(
        project=project,
        register=_RecordingRegister(error=RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        use_case.execute(
            project_id=project.project_id,
            source_relpath="manuales/manual.pdf",
            content=b"pdf",
            actor=PlatformActor(actor_id="operator-1"),
        )

    assert len(storage.calls) == 1
    assert len(register.calls) == 1


def test_upload_raw_falla_cerrado_si_la_politica_rechaza_al_actor() -> None:
    project = _project()
    use_case, storage, register = _use_case(project=project, policy=_DenyAll())

    with pytest.raises(PlatformAccessDenied):
        use_case.execute(
            project_id=project.project_id,
            source_relpath="manuales/manual.pdf",
            content=b"pdf",
            actor=PlatformActor(actor_id="operator-1"),
        )

    assert storage.calls == []
    assert register.calls == []
