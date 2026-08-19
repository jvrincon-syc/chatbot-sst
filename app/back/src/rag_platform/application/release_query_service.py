"""Casos de uso de lectura de releases (superficie Fase 7).

Leer una release por id y listar las releases de un proyecto son lecturas puras
sobre ``rag_releases``: el router HTTP las invoca sin SQL ni reglas de negocio.
La escritura/transición de estado vive en los servicios de draft/build/validate/
publish/retire.
"""

from __future__ import annotations

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.application.release_service import RagReleaseRepository
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import RagRelease


class GetReleaseUseCase:
    """Lee una release por su ``rag_release_id`` (fail-closed por scope).

    La autorización se deriva del **proyecto de la release cargada**, nunca de un
    ``project_id`` que el cliente pudiera suministrar aparte.
    """

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._releases = releases
        self._access_policy = access_policy

    def execute(
        self, rag_release_id: PlatformId, *, actor: PlatformActor
    ) -> RagRelease:
        """Devuelve la release o lanza ``RagReleaseNotFound``/``PlatformAccessDenied``."""

        release = self._releases.get(rag_release_id)
        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=release.project_id
        )
        return release


class ListProjectReleasesUseCase:
    """Lista las releases de un proyecto en orden estable (fail-closed por scope)."""

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._releases = releases
        self._access_policy = access_policy

    def execute(
        self, project_id: PlatformId, *, actor: PlatformActor
    ) -> tuple[RagRelease, ...]:
        """Devuelve las releases del proyecto; actor fuera de scope falla cerrado."""

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        return tuple(self._releases.list_for_project(project_id))
