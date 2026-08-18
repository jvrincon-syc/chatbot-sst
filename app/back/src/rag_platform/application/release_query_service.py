"""Casos de uso de lectura de releases (superficie Fase 7).

Leer una release por id y listar las releases de un proyecto son lecturas puras
sobre ``rag_releases``: el router HTTP las invoca sin SQL ni reglas de negocio.
La escritura/transición de estado vive en los servicios de draft/build/validate/
publish/retire.
"""

from __future__ import annotations

from rag_platform.application.release_service import RagReleaseRepository
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import RagRelease


class GetReleaseUseCase:
    """Lee una release por su ``rag_release_id``."""

    def __init__(self, *, releases: RagReleaseRepository) -> None:
        self._releases = releases

    def execute(self, rag_release_id: PlatformId) -> RagRelease:
        """Devuelve la release o lanza ``RagReleaseNotFound``."""

        return self._releases.get(rag_release_id)


class ListProjectReleasesUseCase:
    """Lista las releases de un proyecto en orden estable."""

    def __init__(self, *, releases: RagReleaseRepository) -> None:
        self._releases = releases

    def execute(self, project_id: PlatformId) -> tuple[RagRelease, ...]:
        """Devuelve las releases del proyecto (orden determinista por id)."""

        return tuple(self._releases.list_for_project(project_id))
