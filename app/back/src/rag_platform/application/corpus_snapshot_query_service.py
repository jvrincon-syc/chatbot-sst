"""Caso de uso de lectura de corpus snapshots de un proyecto (Gate 2, Fase 8).

Listar los snapshots es una lectura pura sobre ``corpus_snapshots``: la GUI la
usa para rehidratar el contexto tras un reload sin inventar estado local. Es
scope-aware (fail-closed) y no expone ningún target físico; el ``CorpusSnapshot``
de dominio solo lleva identidad lógica y membresías por revisión.
"""

from __future__ import annotations

from rag_platform.application.context import (
    CorpusSnapshotRepository,
    PlatformAccessPolicy,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import CorpusSnapshot


class ListProjectCorpusSnapshotsUseCase:
    """Lista los corpus snapshots de un proyecto (orden estable, fail-closed)."""

    def __init__(
        self,
        *,
        snapshots: CorpusSnapshotRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._snapshots = snapshots
        self._access_policy = access_policy

    def execute(
        self, project_id: PlatformId, *, actor: PlatformActor
    ) -> tuple[CorpusSnapshot, ...]:
        """Devuelve los snapshots del proyecto; actor fuera de scope falla cerrado."""

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        return tuple(self._snapshots.list_for_project(project_id))
