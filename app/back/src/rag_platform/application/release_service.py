"""Creación de releases DRAFT y puertos de persistencia de release (Fase 5).

``CreateRagReleaseDraftUseCase`` valida que variante y snapshot son del mismo
proyecto, resuelve un ``target_binding_key`` permitido para el perfil de embedding
de la variante, pinnea los snapshots (variante + corpus + configuración) y crea la
release en ``DRAFT``. No construye artefactos: eso es ``BuildRagReleaseUseCase``.

Los puertos de lectura por id (variante/snapshot/proyecto) y de persistencia de
release/membresía viven aquí y los reusan los otros servicios de Fase 5. Se apoya
en ``TargetBindingResolver`` (Fase 1) para la allowlist de bindings, sin duplicar
esa lógica.

Dirección ``infraestructura → aplicación → dominio``: solo puertos (Protocol) y
modelos de dominio; ningún SDK ni cliente de BD.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Callable, Protocol, Sequence, runtime_checkable

from rag_platform.application.context import TargetBindingResolver
from rag_platform.domain.errors import (
    IncompatibleTargetBinding,
    ReleaseBlockedRevision,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    RagReleaseMembership,
    ReleaseState,
    ensure_same_project,
    next_release_number,
)
from rag_platform.domain.models import (
    CorpusSnapshot,
    EligibilityDecision,
    RagVariant,
)


@runtime_checkable
class RagVariantReader(Protocol):
    """Lectura de una variante por su id (Fase 5)."""

    def get(self, rag_variant_id: PlatformId) -> RagVariant:
        """Devuelve la variante o lanza un error de dominio si no existe."""


@runtime_checkable
class CorpusSnapshotReader(Protocol):
    """Lectura de un corpus snapshot por su id (Fase 5)."""

    def get(self, corpus_snapshot_id: PlatformId) -> CorpusSnapshot:
        """Devuelve el snapshot o lanza un error de dominio si no existe."""


@runtime_checkable
class ProjectConfigurationFingerprintReader(Protocol):
    """Fingerprint de la configuración versionada que congela la release."""

    def configuration_fingerprint(
        self, project_id: PlatformId, configuration_version: int
    ) -> str:
        """Devuelve el fingerprint determinista de la versión ``configuration_version``.

        La versión es la que la release pinneó en su DRAFT; nunca la "vigente",
        para que validar no dependa de mutaciones posteriores de configuración
        (plan Task 4).
        """


@runtime_checkable
class CurrentProjectConfigurationVersionReader(Protocol):
    """Lee la versión de configuración **vigente** de un proyecto.

    Solo se usa al crear un DRAFT para pinnear la versión exacta; una vez
    pinneada, la release nunca vuelve a leer la versión vigente (fail-closed
    contra drift).
    """

    def current_configuration_version(self, project_id: PlatformId) -> int:
        """Devuelve la versión (>=1) vigente o lanza ``ProjectNotFound``."""


@runtime_checkable
class RagReleaseRepository(Protocol):
    """Persistencia de releases (``rag_releases``)."""

    def add(self, release: RagRelease) -> RagRelease:
        """Inserta una release ``DRAFT`` nueva."""

    def get(self, rag_release_id: PlatformId) -> RagRelease:
        """Devuelve la release o lanza un error de dominio si no existe."""

    def list_for_project(self, project_id: PlatformId) -> Sequence[RagRelease]:
        """Devuelve las releases del proyecto en orden estable (por id)."""

    def list_release_numbers(self, rag_variant_id: PlatformId) -> Sequence[int]:
        """Números de release ya usados por la variante (para el siguiente)."""

    def update_state(
        self,
        *,
        rag_release_id: PlatformId,
        state: ReleaseState,
        release_manifest_hash: str | None = None,
        validated_at: datetime | None = None,
        reason: str | None = None,
    ) -> RagRelease:
        """Aplica una transición de estado ya validada por el dominio."""


@runtime_checkable
class RagReleaseMembershipRepository(Protocol):
    """Persistencia de membresías de release (``rag_release_memberships``)."""

    def add(self, membership: RagReleaseMembership) -> RagReleaseMembership:
        """Registra una membresía en el mismo commit lógico que su paso de build."""

    def list_for_release(
        self, rag_release_id: PlatformId
    ) -> Sequence[RagReleaseMembership]:
        """Devuelve las membresías de la release, ordenables por ``ordinal``."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CreateRagReleaseDraftUseCase:
    """Crea una release ``DRAFT`` pinneando variante, snapshot y target binding."""

    def __init__(
        self,
        *,
        variants: RagVariantReader,
        snapshots: CorpusSnapshotReader,
        bindings: TargetBindingResolver,
        releases: RagReleaseRepository,
        configuration_versions: CurrentProjectConfigurationVersionReader,
        release_id_factory: Callable[[], PlatformId],
        clock: Callable[[], datetime] = _now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._variants = variants
        self._snapshots = snapshots
        self._bindings = bindings
        self._releases = releases
        self._configuration_versions = configuration_versions
        self._release_id_factory = release_id_factory
        self._clock = clock
        self._logger = logger

    def execute(
        self,
        *,
        rag_variant_id: PlatformId,
        corpus_snapshot_id: PlatformId,
        target_binding_key: str,
        actor_id: str,
    ) -> RagRelease:
        """Crea la release ``DRAFT``.

        Raises:
            ReleaseProjectMismatch: Si variante y snapshot son de proyectos distintos.
            IncompatibleTargetBinding: Si el binding no está en la allowlist o su
                perfil de embedding no coincide con el de la variante.
            ReleaseBlockedRevision: Si el snapshot contiene una revisión ``blocked``.
        """

        variant = self._variants.get(rag_variant_id)
        snapshot = self._snapshots.get(corpus_snapshot_id)
        ensure_same_project(
            variant_project_id=variant.project_id,
            snapshot_project_id=snapshot.project_id,
        )
        _reject_blocked_revisions(snapshot)

        # Pinnea la versión de configuración vigente en el DRAFT: a partir de aquí
        # el binding se resuelve siempre contra esta versión, no contra la actual.
        configuration_version = (
            self._configuration_versions.current_configuration_version(
                variant.project_id
            )
        )

        binding = self._bindings.find_binding(
            variant.project_id, configuration_version, target_binding_key
        )
        if binding is None:
            raise IncompatibleTargetBinding(
                f"target binding {target_binding_key!r} is not allowed for the project"
            )
        if binding.embedding_profile_id != variant.embedding_profile_id:
            raise IncompatibleTargetBinding(
                "target binding embedding profile does not match the variant recipe"
            )

        release_number = next_release_number(
            existing_numbers=list(self._releases.list_release_numbers(rag_variant_id))
        )
        release = RagRelease(
            rag_release_id=self._release_id_factory(),
            project_id=variant.project_id,
            rag_variant_id=rag_variant_id,
            corpus_snapshot_id=corpus_snapshot_id,
            target_binding_key=target_binding_key,
            configuration_version=configuration_version,
            release_number=release_number,
            state=ReleaseState.DRAFT,
            created_by=actor_id,
            created_at=self._clock(),
        )
        stored = self._releases.add(release)
        if self._logger is not None:
            from rag_platform.application.publication_service import (
                EventStatus,
                emit_release_event,
            )

            emit_release_event(
                logger=self._logger,
                event="rag_release_created",
                status=EventStatus.COMPLETED,
                release=stored,
            )
        return stored


def _reject_blocked_revisions(snapshot: CorpusSnapshot) -> None:
    """Fail-closed si alguna revisión del snapshot está ``blocked``.

    Una ``operator_waiver`` ya es una decisión de elegibilidad válida en el snapshot
    (Fase 2), así que solo ``blocked`` bloquea la release.
    """

    for document in snapshot.documents:
        if document.eligibility_decision is EligibilityDecision.BLOCKED:
            raise ReleaseBlockedRevision(
                "corpus snapshot contains a blocked revision without operator waiver: "
                f"{document.source_document_revision_id.value}"
            )
