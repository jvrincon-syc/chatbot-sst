"""Publicación de releases y eventos de plataforma (Fase 6).

Publicar es una **transición de estado** ``VALIDATED → PUBLISHED``, no una
activación: el catálogo de plataforma acepta la release, pero no se toca
``is_active``, ``retrieval_profiles`` ni el scope legacy ``chatbot/sst-default``.
Este módulo **no** importa ``ConsumerScope``, ``RetrievalProfile`` ni
``ActivateIndexedBundleUseCase`` (test negativo en la suite de neutralidad).

``emit_release_event`` centraliza la emisión de los eventos de ciclo de vida de
release reutilizando ``core.logging.observability`` (redacción de secretos ya
incluida); los ids de release/proyecto viajan en ``attributes``.
"""

from __future__ import annotations

import logging

from core.logging.observability import (
    JsonlEventSink,
    ObservabilityDomain,
    ObservabilityEvent,
    EventStatus,
    emit_observability_event,
)
from indexing.application.bundle_first.ports import TransactionManager
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.application.release_service import RagReleaseRepository
from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.domain.errors import ReleaseManifestFrozen
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    ReleaseState,
    ensure_transition_allowed,
)


def emit_release_event(
    *,
    logger: logging.Logger,
    event: str,
    status: EventStatus,
    release: RagRelease,
    jsonl_sink: JsonlEventSink | None = None,
) -> None:
    """Emite un evento de ciclo de vida de release (ids en ``attributes``).

    Args:
        logger: Logger estructurado destino.
        event: Nombre del evento (``rag_release_published``, ...).
        status: Estado del evento (``COMPLETED``/``REJECTED``/...).
        release: Release afectada (solo ids y estado entran al evento).
        jsonl_sink: Sink JSONL opcional.
    """

    emit_observability_event(
        logger=logger,
        event=ObservabilityEvent(
            event=event,
            domain=ObservabilityDomain.BACKEND,
            status=status,
            message=f"{event} {release.rag_release_id.value}",
            attributes={
                "rag_release_id": release.rag_release_id.value,
                "project_id": release.project_id.value,
                "rag_variant_id": release.rag_variant_id.value,
                "release_state": release.state.value,
            },
        ),
        jsonl_sink=jsonl_sink,
    )


class PublishRagReleaseUseCase:
    """Publica una release ``VALIDATED`` en el catálogo de plataforma."""

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        access_policy: PlatformAccessPolicy,
        transactions: TransactionManager,
        logger: logging.Logger,
        jsonl_sink: JsonlEventSink | None = None,
    ) -> None:
        self._releases = releases
        self._access_policy = access_policy
        self._transactions = transactions
        self._logger = logger
        self._jsonl_sink = jsonl_sink

    def execute(self, *, rag_release_id: PlatformId, actor: PlatformActor) -> RagRelease:
        """Transiciona la release a ``PUBLISHED`` de forma transaccional.

        Raises:
            PlatformAccessDenied: Si el actor no puede operar el proyecto.
            ReleaseManifestFrozen: Si la release no tiene manifiesto congelado
                (no fue validada); una DRAFT no se publica.
            InvalidReleaseTransition: Si el estado actual no permite publicar.
        """

        release = self._releases.get(rag_release_id)
        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=release.project_id
        )
        if not release.is_manifest_frozen:
            # Fail-closed: publicar exige un manifiesto congelado en validación.
            raise ReleaseManifestFrozen(
                f"release {rag_release_id.value} has no frozen manifest to publish"
            )
        ensure_transition_allowed(
            current=release.state, target=ReleaseState.PUBLISHED
        )

        with self._transactions.transaction():
            published = self._releases.update_state(
                rag_release_id=rag_release_id, state=ReleaseState.PUBLISHED
            )
        emit_release_event(
            logger=self._logger,
            event="rag_release_published",
            status=EventStatus.COMPLETED,
            release=published,
            jsonl_sink=self._jsonl_sink,
        )
        return published
