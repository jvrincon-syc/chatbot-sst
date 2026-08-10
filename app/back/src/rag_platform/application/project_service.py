"""Caso de uso de creación de proyecto de plataforma (Fase 1).

Crea un ``RagProject`` con taxonomía documental por plantilla seleccionable,
política de organización de corpus y raíces de almacenamiento aisladas. La
plantilla SST es seleccionable pero no se preselecciona (plan §Fase 1); solo
``sst-general`` parte de la plantilla SST versionada.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion.schemas.common import StrictModel
from pydantic import Field

from rag_platform.application.context import (
    PlatformAccessPolicy,
    ProjectRepository,
    StorageRootsProvider,
)
from rag_platform.domain.errors import ProjectAlreadyExists, UnknownDocumentTypeTemplate
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    DocumentTypeTemplate,
    ProjectConfiguration,
    ProjectDocumentType,
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
    RagProject,
)


#: Tipos documentales neutrales de la plantilla ``GENERIC`` (única por defecto).
_GENERIC_DOCUMENT_TYPES: tuple[ProjectDocumentType, ...] = (
    ProjectDocumentType(
        code="document", display_name="Documento", template=DocumentTypeTemplate.GENERIC
    ),
    ProjectDocumentType(
        code="form", display_name="Formulario", template=DocumentTypeTemplate.GENERIC
    ),
    ProjectDocumentType(
        code="record", display_name="Registro", template=DocumentTypeTemplate.GENERIC
    ),
)

#: Taxonomía SST versionada; base de ``sst-general`` (plan §Fase 1).
_SST_DOCUMENT_TYPES: tuple[ProjectDocumentType, ...] = (
    ProjectDocumentType(
        code="procedimiento",
        display_name="Procedimiento",
        template=DocumentTypeTemplate.SST,
    ),
    ProjectDocumentType(
        code="instructivo",
        display_name="Instructivo",
        template=DocumentTypeTemplate.SST,
    ),
    ProjectDocumentType(
        code="formato", display_name="Formato", template=DocumentTypeTemplate.SST
    ),
    ProjectDocumentType(
        code="matriz", display_name="Matriz", template=DocumentTypeTemplate.SST
    ),
    ProjectDocumentType(
        code="politica", display_name="Política", template=DocumentTypeTemplate.SST
    ),
)

_TEMPLATE_DOCUMENT_TYPES: dict[DocumentTypeTemplate, tuple[ProjectDocumentType, ...]] = {
    DocumentTypeTemplate.GENERIC: _GENERIC_DOCUMENT_TYPES,
    DocumentTypeTemplate.SST: _SST_DOCUMENT_TYPES,
}


class CreateProjectRequest(StrictModel):
    """Entrada validada para crear un proyecto.

    ``actor_id`` no forma parte del request: se pasa como argumento explícito del
    caso de uso desde una identidad autenticada (invariante §8 del plan).
    """

    project_slug: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    document_type_template: DocumentTypeTemplate = DocumentTypeTemplate.GENERIC
    corpus_organization_policy: CorpusOrganizationPolicy = (
        CorpusOrganizationPolicy.SOURCE_FOLDERS_V1
    )
    embedding_profiles: tuple[ProjectEmbeddingProfile, ...] = Field(
        default_factory=tuple
    )
    target_bindings: tuple[ProjectIndexingTargetBinding, ...] = Field(
        default_factory=tuple
    )


class CreateProjectUseCase:
    """Crea un proyecto aislado con su configuración versionada inicial."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        storage_roots: StorageRootsProvider,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._projects = projects
        self._storage_roots = storage_roots
        self._access_policy = access_policy

    def execute(self, request: CreateProjectRequest, *, actor_id: str) -> RagProject:
        """Crea y persiste un proyecto nuevo.

        Args:
            request: Datos validados del proyecto a crear.
            actor_id: Operador autenticado; autorizado por ``PlatformAccessPolicy``.

        Returns:
            El ``RagProject`` persistido.

        Raises:
            PlatformAccessDenied: Si el actor no es operador autorizado.
            ProjectAlreadyExists: Si el ``project_id`` ya existe.
            UnknownDocumentTypeTemplate: Si la plantilla no está registrada.
        """

        self._access_policy.require_operator(actor_id=actor_id)

        project_id = PlatformId(
            kind=IdentityKind.PROJECT, value=f"{IdentityKind.PROJECT.value}_{request.project_slug}"
        )
        if self._projects.exists(project_id):
            raise ProjectAlreadyExists(project_id.value)

        try:
            document_types = _TEMPLATE_DOCUMENT_TYPES[request.document_type_template]
        except KeyError as error:
            raise UnknownDocumentTypeTemplate(
                request.document_type_template.value
            ) from error

        now = datetime.now(timezone.utc)
        configuration = ProjectConfiguration(
            version=1,
            document_types=document_types,
            embedding_profiles=request.embedding_profiles,
            target_bindings=request.target_bindings,
            corpus_organization_policy=request.corpus_organization_policy,
            created_at=now,
        )
        project = RagProject(
            project_id=project_id,
            display_name=request.display_name,
            storage_roots=self._storage_roots.roots_for(project_id),
            configuration=configuration,
            created_at=now,
        )
        return self._projects.add(project)
