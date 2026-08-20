"""Read-model de documentos de un proyecto para la GUI (Gate 1, Fase 8).

Listar los documentos de un proyecto es una lectura pura sobre las revisiones
inmutables (``source_document_revisions``) cruzada con el catálogo de
normalizados para derivar el estado de procesamiento. **No** devuelve rutas
físicas: la GUI solo necesita la identidad lógica (``srev_``/``doc_``), el
``source_relpath`` lógico, el tamaño y el estado. La autorización es fail-closed
por scope de proyecto, igual que el resto de la superficie de lectura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rag_platform.application.context import (
    NormalizedArtifactRepository,
    PlatformAccessPolicy,
    SourceDocumentRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.identity import PlatformId


@dataclass(frozen=True)
class ProjectDocumentRevisionRow:
    """Fila del read-model de documentos de un proyecto (sin rutas físicas)."""

    source_document_revision_id: str
    logical_document_id: str
    source_relpath: str
    file_size: int
    review_state: str
    uploaded_at: datetime
    raw_registered: bool
    normalized_registered: bool
    processing_status: str


class ListProjectDocumentsUseCase:
    """Lista las revisiones de un proyecto con su estado de normalización."""

    def __init__(
        self,
        *,
        documents: SourceDocumentRepository,
        normalized: NormalizedArtifactRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._documents = documents
        self._normalized = normalized
        self._access_policy = access_policy

    def execute(
        self, project_id: PlatformId, *, actor: PlatformActor
    ) -> tuple[ProjectDocumentRevisionRow, ...]:
        """Devuelve el read-model del proyecto; fuera de scope falla cerrado."""

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        revisions = self._documents.list_revisions_for_project(project_id)
        normalized_ids = self._normalized.list_normalized_revision_ids(project_id)
        rows: list[ProjectDocumentRevisionRow] = []
        for revision in revisions:
            revision_id = revision.source_document_revision_id.value
            is_normalized = revision_id in normalized_ids
            rows.append(
                ProjectDocumentRevisionRow(
                    source_document_revision_id=revision_id,
                    logical_document_id=revision.logical_document_id.value,
                    source_relpath=revision.source_relpath,
                    file_size=revision.file_size,
                    review_state=revision.review_state.value,
                    uploaded_at=revision.uploaded_at,
                    # ponytail: toda revisión listada nació del path de registro raw
                    # (upload/CLI), así que su sidecar físico existe por construcción.
                    raw_registered=True,
                    normalized_registered=is_normalized,
                    processing_status="normalized" if is_normalized else "registered",
                )
            )
        return tuple(rows)
