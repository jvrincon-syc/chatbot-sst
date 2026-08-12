"""Orquestador de registro de ``raw`` por proyecto (Fase 2, Task 4).

``RegisterProjectRawArtifactUseCase`` **compone** piezas existentes; no
reimplementa el motor de ingesta ni el pipeline legacy:

1. crea o reutiliza la revisión lógica inmutable vía
   ``CreateSourceDocumentRevisionUseCase`` (identidad ``srev_`` determinista);
2. deriva la ruta física desde la raíz declarada del proyecto
   (``storage_roots.raw``), de modo que el drift ``raw``/``docs_raw`` sea
   catalog-driven y no una constante;
3. hace ``upsert`` del sidecar físico en ``project_raw_document_artifacts``.

``project_id`` es identidad obligatoria del artefacto; el orquestador falla
cerrado (``ProjectNotFound``) si el proyecto no está registrado. La dirección de
dependencias se respeta: este servicio solo conoce puertos de aplicación y el
dominio, nunca PostgreSQL, FastAPI ni SDKs.
"""

from __future__ import annotations

import logging

from ingestion.schemas.common import RelativePosixPath, StrictModel
from pydantic import Field

from rag_platform.application.context import (
    ProjectRepository,
    RawArtifactCatalogRepository,
)
from rag_platform.application.document_revision_service import (
    CreateSourceDocumentRevisionUseCase,
    RegisterRevisionRequest,
)
from rag_platform.domain.artifact_catalog import RawDocumentArtifactRecord
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import RevisionReviewState, SourceDocumentRevision


_LOGGER = logging.getLogger(__name__)

#: Nombre de la raíz declarada donde viven los bytes originales del proyecto.
_RAW_ROOT_NAME = "raw"


class RegisterProjectRawArtifactRequest(StrictModel):
    """Entrada validada para registrar un artefacto ``raw`` por proyecto.

    ``raw_content_hash`` es un SHA-256 (64 hex) porque el catálogo físico lo exige
    como identidad de bytes; ``actor_id`` viaja como argumento explícito del caso
    de uso, nunca desde un body no autenticado.
    """

    project_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    raw_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=0)
    review_state: RevisionReviewState = RevisionReviewState.PROCESSED


class RegisterProjectRawArtifactUseCase:
    """Compone revisión lógica y catálogo físico de ``raw`` por proyecto."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        revisions: CreateSourceDocumentRevisionUseCase,
        raw_catalog: RawArtifactCatalogRepository,
    ) -> None:
        self._projects = projects
        self._revisions = revisions
        self._raw_catalog = raw_catalog

    def execute(
        self, request: RegisterProjectRawArtifactRequest, *, actor_id: str
    ) -> SourceDocumentRevision:
        """Registra la revisión y el sidecar físico raw de forma idempotente.

        Args:
            request: Datos validados del artefacto raw.
            actor_id: Operador autenticado; queda como ``uploaded_by``.

        Returns:
            La ``SourceDocumentRevision`` creada o reutilizada.

        Raises:
            ProjectNotFound: Si el proyecto no está registrado (fail-closed).
        """

        # Fail-closed antes de crear identidad: el proyecto debe existir y su
        # raíz declarada es la autoridad de la ubicación física.
        project = self._projects.get(
            PlatformId(
                kind=IdentityKind.PROJECT,
                value=f"{IdentityKind.PROJECT.value}_{request.project_id}",
            )
        )

        revision = self._revisions.execute(
            RegisterRevisionRequest(
                project_id=request.project_id,
                source_relpath=request.source_relpath,
                raw_content_hash=request.raw_content_hash,
                file_size=request.file_size,
                review_state=request.review_state,
            ),
            actor_id=actor_id,
        )

        raw_root = getattr(project.storage_roots, _RAW_ROOT_NAME)
        artifact_relpath = f"{raw_root}/{request.source_relpath}"
        record = RawDocumentArtifactRecord(
            project_id=revision.project_id.value,
            source_document_revision_id=revision.source_document_revision_id.value,
            logical_document_id=revision.logical_document_id.value,
            artifact_relpath=artifact_relpath,
            source_relpath=request.source_relpath,
            raw_content_hash=request.raw_content_hash,
            file_size=request.file_size,
            uploaded_by=revision.uploaded_by,
            uploaded_at=revision.uploaded_at,
        )
        self._raw_catalog.upsert(record)

        _LOGGER.info(
            "registered project raw artifact",
            extra={
                "project_id": revision.project_id.value,
                "document_id": revision.logical_document_id.value,
                "source_document_revision_id": revision.source_document_revision_id.value,
                "capability": "ingestion.raw_catalog",
                "status": "registered",
            },
        )
        return revision
