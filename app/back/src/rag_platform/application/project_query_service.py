"""Casos de uso de lectura y metadatos de proyectos (superficie Fase 7).

Estos casos de uso son la superficie que el router HTTP de Fase 7 invoca sin
escribir SQL ni reglas de negocio: listar proyectos, leerlos, editar sus
metadatos y listar los perfiles de procesamiento/chunking del proyecto. La
identidad ``project_id`` es inmutable; solo ``display_name`` es editable
(ADR-006 §2.1). Toda mutación pasa por ``PlatformAccessPolicy`` fail-closed.
"""

from __future__ import annotations

from rag_platform.application.context import (
    ChunkingProfileRepository,
    PlatformAccessPolicy,
    ProcessingProfileRepository,
    ProjectRepository,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    DocumentProcessingProfile,
    RagProject,
)


class ListProjectsUseCase:
    """Lista todos los proyectos del catálogo con su configuración vigente."""

    def __init__(self, *, projects: ProjectRepository) -> None:
        self._projects = projects

    def execute(self) -> tuple[RagProject, ...]:
        """Devuelve el catálogo completo de proyectos."""

        return self._projects.list_all()


class GetProjectUseCase:
    """Lee un proyecto por su ``project_id``."""

    def __init__(self, *, projects: ProjectRepository) -> None:
        self._projects = projects

    def execute(self, project_id: PlatformId) -> RagProject:
        """Devuelve el proyecto o lanza ``ProjectNotFound``."""

        return self._projects.get(project_id)


class UpdateProjectMetadataUseCase:
    """Edita los metadatos mutables de un proyecto (solo ``display_name``)."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._projects = projects
        self._access_policy = access_policy

    def execute(
        self, project_id: PlatformId, *, display_name: str, actor_id: str
    ) -> RagProject:
        """Actualiza el ``display_name`` de un proyecto existente.

        Args:
            project_id: Proyecto a editar; su identidad no cambia.
            display_name: Nuevo nombre legible.
            actor_id: Operador autenticado; autorizado por ``PlatformAccessPolicy``.

        Returns:
            El ``RagProject`` con los metadatos actualizados.

        Raises:
            PlatformAccessDenied: Si el actor no es operador autorizado.
            ProjectNotFound: Si el proyecto no está registrado.
        """

        self._access_policy.require_operator(actor_id=actor_id)
        return self._projects.update_metadata(
            project_id, display_name=display_name
        )


class ListProcessingProfilesUseCase:
    """Lista los perfiles de procesamiento declarados por un proyecto."""

    def __init__(
        self, *, processing_profiles: ProcessingProfileRepository
    ) -> None:
        self._processing_profiles = processing_profiles

    def execute(
        self, project_id: PlatformId
    ) -> tuple[DocumentProcessingProfile, ...]:
        """Devuelve los perfiles de procesamiento del proyecto."""

        return self._processing_profiles.list_for_project(project_id)


class ListChunkingProfilesUseCase:
    """Lista los perfiles de chunking declarados por un proyecto."""

    def __init__(self, *, chunking_profiles: ChunkingProfileRepository) -> None:
        self._chunking_profiles = chunking_profiles

    def execute(self, project_id: PlatformId) -> tuple[ChunkingProfile, ...]:
        """Devuelve los perfiles de chunking del proyecto."""

        return self._chunking_profiles.list_for_project(project_id)
