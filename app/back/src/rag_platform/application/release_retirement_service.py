"""Retiro formal de una release (superficie Fase 7).

Retirar es una transición de estado ``VALIDATED | PUBLISHED → RETIRED`` con actor
de confianza y motivo, fail-closed:

- el actor viene de la frontera server-side (``PlatformActor``), nunca de un body;
- la transición la valida el lifecycle de dominio (``ensure_transition_allowed``);
- ``RETIRED`` es terminal: una release retirada no vuelve a ningún estado.

No borra artefactos ni membresías: el retiro es un cambio de estado observable y
auditable, no una eliminación.
"""

from __future__ import annotations

import logging

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.application.release_service import RagReleaseRepository
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    ReleaseState,
    ensure_transition_allowed,
)


class RetireRagReleaseUseCase:
    """Transiciona una release a ``RETIRED`` con actor y motivo (fail-closed)."""

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        access_policy: PlatformAccessPolicy,
        logger: logging.Logger | None = None,
    ) -> None:
        self._releases = releases
        self._access_policy = access_policy
        self._logger = logger

    def execute(
        self,
        *,
        rag_release_id: PlatformId,
        actor: PlatformActor,
        reason: str,
    ) -> RagRelease:
        """Retira la release.

        Raises:
            RagReleaseNotFound: Si la release no existe.
            PlatformAccessDenied: Si el actor no puede operar el proyecto.
            InvalidReleaseTransition: Si el estado actual no admite ``RETIRED``
                (p. ej. una ``DRAFT`` o una ya ``FAILED``/``RETIRED``).
        """

        release = self._releases.get(rag_release_id)
        require_project_operator(
            policy=self._access_policy,
            actor=actor,
            project_id=release.project_id,
        )
        ensure_transition_allowed(
            current=release.state, target=ReleaseState.RETIRED
        )
        retired = self._releases.update_state(
            rag_release_id=rag_release_id,
            state=ReleaseState.RETIRED,
            reason=reason,
        )
        if self._logger is not None:
            from rag_platform.application.publication_service import (
                EventStatus,
                emit_release_event,
            )

            emit_release_event(
                logger=self._logger,
                event="rag_release_retired",
                status=EventStatus.COMPLETED,
                release=retired,
            )
        return retired
