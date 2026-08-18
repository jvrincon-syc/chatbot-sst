"""Validación de release: completitud, integridad y congelado del manifiesto (Fase 5).

``ValidateRagReleaseUseCase`` comprueba que cada revisión del corpus snapshot tiene
su membresía con artefactos concretos del mismo proyecto, congela el
``release_manifest_hash`` de forma determinista y transiciona la release a
``VALIDATED``. Una release ya validada no se muta en sitio: un cambio de corpus o
receta obliga a un snapshot nuevo antes de revalidar (fail-closed).

Reusa ``compute_release_manifest_hash`` (dominio) y las guardas de transición; no
reimplementa hashing ni lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Callable

from rag_platform.application.release_service import (
    CorpusSnapshotReader,
    ProjectConfigurationFingerprintReader,
    RagReleaseMembershipRepository,
    RagReleaseRepository,
    RagVariantReader,
)
from rag_platform.domain.errors import (
    ReleaseBlockedRevision,
    ReleaseManifestFrozen,
    ReleaseNotComplete,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    ReleaseState,
    compute_release_manifest_hash,
    ensure_transition_allowed,
)
from rag_platform.domain.models import CorpusSnapshot, EligibilityDecision


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ValidateRagReleaseUseCase:
    """Valida una release DRAFT y congela su manifiesto."""

    def __init__(
        self,
        *,
        releases: RagReleaseRepository,
        variants: RagVariantReader,
        snapshots: CorpusSnapshotReader,
        memberships: RagReleaseMembershipRepository,
        configuration_fingerprints: ProjectConfigurationFingerprintReader,
        clock: Callable[[], datetime] = _now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._releases = releases
        self._variants = variants
        self._snapshots = snapshots
        self._memberships = memberships
        self._configuration_fingerprints = configuration_fingerprints
        self._clock = clock
        self._logger = logger

    def execute(self, *, rag_release_id: PlatformId, actor_id: str) -> RagRelease:
        """Valida la release y la transiciona a ``VALIDATED``.

        Raises:
            ReleaseManifestFrozen: Si la release ya tiene manifiesto congelado.
            ReleaseNotComplete: Si falta la membresía de alguna revisión.
            ReleaseBlockedRevision: Si el snapshot contiene una revisión ``blocked``.
            InvalidReleaseTransition: Si la release no está en ``DRAFT``.
        """

        release = self._releases.get(rag_release_id)
        if release.is_manifest_frozen:
            raise ReleaseManifestFrozen(
                f"release {rag_release_id.value} manifest is already frozen"
            )
        ensure_transition_allowed(
            current=release.state, target=ReleaseState.VALIDATED
        )

        variant = self._variants.get(release.rag_variant_id)
        snapshot = self._snapshots.get(release.corpus_snapshot_id)
        _reject_blocked_revisions(snapshot)

        memberships = sorted(
            self._memberships.list_for_release(rag_release_id),
            key=lambda member: member.ordinal,
        )
        _assert_complete(snapshot=snapshot, memberships=memberships)

        manifest_hash = compute_release_manifest_hash(
            project_id=release.project_id.value,
            rag_variant_id=release.rag_variant_id.value,
            corpus_snapshot_id=release.corpus_snapshot_id.value,
            corpus_manifest_hash=snapshot.manifest_hash,
            semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
            configuration_fingerprint=self._configuration_fingerprints.configuration_fingerprint(
                release.project_id, release.configuration_version
            ),
            target_binding_key=release.target_binding_key,
            memberships=memberships,
        )
        validated = self._releases.update_state(
            rag_release_id=rag_release_id,
            state=ReleaseState.VALIDATED,
            release_manifest_hash=manifest_hash,
            validated_at=self._clock(),
        )
        if self._logger is not None:
            from rag_platform.application.publication_service import (
                EventStatus,
                emit_release_event,
            )

            emit_release_event(
                logger=self._logger,
                event="rag_release_validated",
                status=EventStatus.COMPLETED,
                release=validated,
            )
        return validated


def _reject_blocked_revisions(snapshot: CorpusSnapshot) -> None:
    """Fail-closed si alguna revisión del snapshot está ``blocked``."""

    for document in snapshot.documents:
        if document.eligibility_decision is EligibilityDecision.BLOCKED:
            raise ReleaseBlockedRevision(
                "corpus snapshot contains a blocked revision without operator waiver: "
                f"{document.source_document_revision_id.value}"
            )


def _assert_complete(*, snapshot: CorpusSnapshot, memberships) -> None:
    """Fail-closed si falta la membresía de alguna revisión del snapshot."""

    expected = {doc.source_document_revision_id.value for doc in snapshot.documents}
    present = {member.source_document_revision_id.value for member in memberships}
    missing = expected - present
    if missing:
        raise ReleaseNotComplete(
            f"release is missing memberships for revisions: {sorted(missing)}"
        )
