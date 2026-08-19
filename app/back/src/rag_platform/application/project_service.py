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
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
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
    ProjectDocumentType(
        code="manual", display_name="Manual", template=DocumentTypeTemplate.GENERIC
        ),
    ProjectDocumentType(
        code="acta", display_name="Acta", template=DocumentTypeTemplate.GENERIC
            ),
    ProjectDocumentType(
        code="informe", display_name="Informe", template=DocumentTypeTemplate.GENERIC
                ),
    ProjectDocumentType(
        code="guia", display_name="Guia", template=DocumentTypeTemplate.GENERIC
        ),
    )


#: Taxonomía SST versionada; base de ``sst-general`` (plan §Fase 1).
#: Los ``code`` coinciden **exactamente** con las etiquetas que emite el
#: clasificador SST legacy (``ingestion.classification.rules`` / el ``Literal``
#: ``DocumentType`` de ``ingestion.schemas.artifacts``), de modo que
#: ``resolve_document_type`` valide una clasificación SST real sin rechazarla
#: fail-closed (plan §Fase 2, items de política documental). Desajuste plan/código
#: resuelto: la plantilla previa (5 códigos, con ``formato`` en vez de
#: ``formulario``) no cubría las decisiones del clasificador.
_SST_DOCUMENT_TYPES: tuple[ProjectDocumentType, ...] = tuple(
    ProjectDocumentType(code=code, display_name=display_name, template=DocumentTypeTemplate.SST)
    for code, display_name in (
        ("manual", "Manual"),
        ("formulario", "Formulario"),
        ("politica", "Política"),
        ("reglamento", "Reglamento"),
        ("programa", "Programa"),
        ("matriz", "Matriz"),
        ("procedimiento", "Procedimiento"),
        ("anexo", "Anexo"),
        ("instructivo", "Instructivo"),
        ("capacitacion", "Capacitación"),
        ("acta", "Acta"),
        ("norma", "Norma"),
        ("guia", "Guía"),
        ("informacion_general", "Información general"),
        ("otro", "Otro"),
    )
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

    def execute(
        self, request: CreateProjectRequest, *, actor: PlatformActor
    ) -> RagProject:
        """Crea y persiste un proyecto nuevo.

        Args:
            request: Datos validados del proyecto a crear.
            actor: Actor de confianza server-side; autorizado por
                ``require_project_operator`` (operador + scope de proyecto).

        Returns:
            El ``RagProject`` persistido.

        Raises:
            PlatformAccessDenied: Si el actor no es operador o el proyecto está
                fuera de su scope.
            ProjectAlreadyExists: Si el ``project_id`` ya existe.
            UnknownDocumentTypeTemplate: Si la plantilla no está registrada.
        """

        project_id = PlatformId(
            kind=IdentityKind.PROJECT, value=f"{IdentityKind.PROJECT.value}_{request.project_slug}"
        )
        # Frontera uniforme: un actor scoped no puede crear proyectos fuera de su
        # scope (fail-closed hacia SSO/RBAC).
        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
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
