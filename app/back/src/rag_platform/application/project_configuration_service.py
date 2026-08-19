"""Casos de uso de configuración versionada de proyecto (superficie Fase 7).

La configuración de un proyecto es **versionada e inmutable por versión**: cada
edición materializa una versión nueva (``version`` monótona) para poder congelar
la configuración exacta que usó una receta o release. Estos casos de uso leen la
versión vigente, leen una versión histórica exacta (incluidos sus
``target_bindings`` por versión, sin colapsarlos en la última) y crean una
versión nueva. Toda creación pasa por ``PlatformAccessPolicy`` fail-closed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion.schemas.common import StrictModel
from pydantic import Field

from rag_platform.application.context import (
    PlatformAccessPolicy,
    ProjectConfigurationRepository,
    ProjectRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    ProjectConfiguration,
    ProjectDocumentType,
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
)


class UpdateProjectConfigurationRequest(StrictModel):
    """Entrada validada para materializar una versión nueva de configuración.

    ``version`` no forma parte del request: la asigna el caso de uso de forma
    monótona a partir de la versión vigente, para que el cliente nunca elija ni
    reescriba una versión existente.
    """

    corpus_organization_policy: CorpusOrganizationPolicy
    document_types: tuple[ProjectDocumentType, ...] = Field(default_factory=tuple)
    embedding_profiles: tuple[ProjectEmbeddingProfile, ...] = Field(
        default_factory=tuple
    )
    target_bindings: tuple[ProjectIndexingTargetBinding, ...] = Field(
        default_factory=tuple
    )


class GetProjectConfigurationUseCase:
    """Lee la configuración **vigente** (última versión) de un proyecto."""

    def __init__(self, *, projects: ProjectRepository) -> None:
        self._projects = projects

    def execute(self, project_id: PlatformId) -> ProjectConfiguration:
        """Devuelve la configuración vigente o lanza ``ProjectNotFound``."""

        return self._projects.get(project_id).configuration


class GetProjectConfigurationVersionUseCase:
    """Lee una versión histórica exacta de la configuración de un proyecto.

    Preserva los ``target_bindings`` de esa versión: no los colapsa en la última
    (plan Task 3, lectura version-aware por ``(project_id, version, binding_key)``).
    """

    def __init__(
        self, *, configurations: ProjectConfigurationRepository
    ) -> None:
        self._configurations = configurations

    def execute(
        self, project_id: PlatformId, *, version: int
    ) -> ProjectConfiguration:
        """Devuelve la configuración exacta de ``version``.

        Raises:
            ProjectNotFound: Si el proyecto o la versión no existen.
        """

        return self._configurations.get_version(project_id, version)


class CreateProjectConfigurationVersionUseCase:
    """Materializa una versión nueva de la configuración de un proyecto."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        configurations: ProjectConfigurationRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._projects = projects
        self._configurations = configurations
        self._access_policy = access_policy

    def execute(
        self,
        project_id: PlatformId,
        *,
        request: UpdateProjectConfigurationRequest,
        actor: PlatformActor,
    ) -> ProjectConfiguration:
        """Crea y persiste una versión nueva a partir de la vigente.

        Args:
            project_id: Proyecto cuya configuración se edita.
            request: Datos validados de la nueva configuración.
            actor: Actor de confianza server-side; autorizado por
                ``require_project_operator`` (operador + scope de proyecto).

        Returns:
            La ``ProjectConfiguration`` recién versionada.

        Raises:
            PlatformAccessDenied: Si el actor no es operador o el proyecto está
                fuera de su scope.
            ProjectNotFound: Si el proyecto no está registrado.
        """

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        current = self._projects.get(project_id).configuration
        new_configuration = ProjectConfiguration(
            version=current.version + 1,
            document_types=request.document_types,
            embedding_profiles=request.embedding_profiles,
            target_bindings=request.target_bindings,
            corpus_organization_policy=request.corpus_organization_policy,
            created_at=datetime.now(timezone.utc),
        )
        return self._configurations.create_version(project_id, new_configuration)
