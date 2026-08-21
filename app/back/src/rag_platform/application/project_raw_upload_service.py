"""Upload de bytes ``raw`` por proyecto vía HTTP (Gate 1, Fase 8).

Compone (no reimplementa): valida el actor por scope, calcula la identidad de
bytes (SHA-256 + tamaño) server-side, persiste los bytes bajo la raíz ``raw`` del
proyecto vía el puerto ``ProjectRawStorage`` y delega la identidad lógica y el
sidecar físico en ``RegisterProjectRawArtifactUseCase``. El ``actor_id`` viene del
principal autenticado, nunca del form (invariante §Actor). Fail-closed:
``ProjectNotFound`` si el proyecto no existe, ``UnsafeArtifactPath`` si el
``source_relpath`` intenta traversal.
"""

from __future__ import annotations

from hashlib import sha256
import logging

from rag_platform.application.context import (
    PlatformAccessPolicy,
    ProjectRawStorage,
    ProjectRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.application.raw_ingestion_service import (
    RegisterProjectRawArtifactRequest,
    RegisterProjectRawArtifactUseCase,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import SourceDocumentRevision


_LOGGER = logging.getLogger(__name__)


class UploadProjectRawDocumentUseCase:
    """Persiste bytes subidos y registra la revisión raw del proyecto."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        storage: ProjectRawStorage,
        register: RegisterProjectRawArtifactUseCase,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._projects = projects
        self._storage = storage
        self._register = register
        self._access_policy = access_policy

    def execute(
        self,
        *,
        project_id: PlatformId,
        source_relpath: str,
        content: bytes,
        actor: PlatformActor,
    ) -> SourceDocumentRevision:
        """Sube un documento raw y devuelve su revisión inmutable.

        El hash y el tamaño se calculan aquí (server-side), nunca se aceptan del
        cliente. Los bytes se escriben antes de registrar: si el registro falla, el
        sidecar físico ya persistido queda re-vinculado en un reintento idempotente
        (mismo hash → misma revisión).
        """

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        # Fail-closed antes de tocar disco: el proyecto debe existir y su raíz
        # declarada es la autoridad de la ubicación física.
        project = self._projects.get(project_id)

        raw_content_hash = sha256(content).hexdigest()
        _LOGGER.info(
            "uploading project raw document",
            extra={
                "project_id": project_id.value,
                "source_relpath": source_relpath,
                "file_size": len(content),
                "actor_id": actor.actor_id,
                "capability": "ingestion.raw_upload",
                "status": "started",
            },
        )
        # Escribe validando contención (traversal → UnsafeArtifactPath) antes de
        # crear identidad lógica.
        self._storage.write_raw_bytes(project, source_relpath, content)

        slug = project_id.value[len(f"{IdentityKind.PROJECT.value}_") :]
        revision = self._register.execute(
            RegisterProjectRawArtifactRequest(
                project_id=slug,
                source_relpath=source_relpath,
                raw_content_hash=raw_content_hash,
                file_size=len(content),
            ),
            actor_id=actor.actor_id,
        )
        _LOGGER.info(
            "uploaded project raw document",
            extra={
                "project_id": revision.project_id.value,
                "logical_document_id": revision.logical_document_id.value,
                "source_document_revision_id": revision.source_document_revision_id.value,
                "source_relpath": revision.source_relpath,
                "raw_content_hash": raw_content_hash,
                "capability": "ingestion.raw_upload",
                "status": "completed",
            },
        )
        return revision
