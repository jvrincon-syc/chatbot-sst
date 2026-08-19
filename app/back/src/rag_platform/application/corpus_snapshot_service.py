"""Caso de uso de creación de corpus snapshots (Fase 2).

Congela una lista ordenada e inmutable de revisiones de un proyecto con un
``manifest_hash`` determinista reconstruible solo con las filas. Fail-closed:

- una revisión ``needs_review`` sin decisión de elegibilidad válida
  (``approved_after_review`` u ``operator_waiver``) se rechaza;
- una decisión ``blocked`` se rechaza siempre.

Cualquier cambio material de selección (revisión distinta, o distinta decisión de
elegibilidad) produce otro ``manifest_hash`` y, por tanto, otro snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from rag_platform.application.context import (
    CorpusSnapshotRepository,
    PlatformAccessPolicy,
    SourceDocumentRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.errors import (
    DuplicateRevisionInSnapshot,
    EmptyCorpusSnapshot,
    RevisionNotReleaseEligible,
    RevisionProjectMismatch,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusSnapshot,
    CorpusSnapshotDocument,
    EligibilityDecision,
    RevisionReviewState,
    compute_corpus_manifest_hash,
)


#: Decisiones que hacen releaseable una revisión ``needs_review``.
_ELIGIBLE_OVERRIDES = frozenset(
    {EligibilityDecision.APPROVED_AFTER_REVIEW, EligibilityDecision.OPERATOR_WAIVER}
)


class CreateCorpusSnapshotUseCase:
    """Crea un corpus snapshot inmutable a partir de revisiones elegibles."""

    def __init__(
        self,
        *,
        snapshots: CorpusSnapshotRepository,
        documents: SourceDocumentRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._snapshots = snapshots
        self._documents = documents
        self._access_policy = access_policy

    def execute(
        self,
        *,
        project_id: str,
        document_revision_ids: Sequence[str],
        actor: PlatformActor,
        eligibility_decisions: Mapping[str, EligibilityDecision] | None = None,
    ) -> CorpusSnapshot:
        """Congela un corpus snapshot determinista.

        Args:
            project_id: Slug del proyecto propietario (sin prefijo ``proj_``).
            document_revision_ids: Ids ``srev_`` de las revisiones a incluir.
            actor: Actor de confianza server-side; autorizado por
                ``require_project_operator`` (operador + scope de proyecto).
            eligibility_decisions: Decisión explícita por ``revision_id`` para las
                revisiones que la requieran (``needs_review``).

        Returns:
            El ``CorpusSnapshot`` congelado (o el preexistente con el mismo hash).

        Raises:
            PlatformAccessDenied: Si el actor no es operador o el proyecto está
                fuera de su scope.
            EmptyCorpusSnapshot: Si no se pasa ninguna revisión.
            DuplicateRevisionInSnapshot: Si una revisión aparece dos veces.
            RevisionProjectMismatch: Si una revisión es de otro proyecto.
            RevisionNotReleaseEligible: Si una ``needs_review`` no tiene decisión
                válida, o si su decisión es ``blocked``.
        """

        if not document_revision_ids:
            raise EmptyCorpusSnapshot(project_id)
        if len(set(document_revision_ids)) != len(document_revision_ids):
            raise DuplicateRevisionInSnapshot(project_id)

        project = PlatformId(
            kind=IdentityKind.PROJECT,
            value=f"{IdentityKind.PROJECT.value}_{project_id}",
        )
        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project
        )
        decisions = eligibility_decisions or {}

        members: list[CorpusSnapshotDocument] = []
        # Orden determinista: el orden de entrada define el ordinal, estable y
        # reconstruible desde las filas persistidas.
        for ordinal, revision_id in enumerate(document_revision_ids):
            revision_pid = PlatformId(
                kind=IdentityKind.SOURCE_DOCUMENT_REVISION, value=revision_id
            )
            revision = self._documents.get_revision(revision_pid)
            if revision.project_id != project:
                raise RevisionProjectMismatch(revision_id)

            decision = self._resolve_decision(
                revision_id=revision_id,
                review_state=revision.review_state,
                explicit=decisions.get(revision_id),
            )
            members.append(
                CorpusSnapshotDocument(
                    ordinal=ordinal,
                    source_document_revision_id=revision_pid,
                    eligibility_decision=decision,
                )
            )

        manifest_hash = compute_corpus_manifest_hash(
            project_id=project.value, documents=members
        )

        # Idempotencia: el mismo conjunto ordenado + decisiones ⇒ mismo snapshot.
        existing = self._snapshots.find_by_manifest(project, manifest_hash)
        if existing is not None:
            return existing

        snapshot = CorpusSnapshot(
            corpus_snapshot_id=PlatformId(
                kind=IdentityKind.CORPUS_SNAPSHOT,
                value=f"{IdentityKind.CORPUS_SNAPSHOT.value}_{manifest_hash[:24]}",
            ),
            project_id=project,
            documents=tuple(members),
            document_count=len(members),
            manifest_hash=manifest_hash,
            created_at=datetime.now(timezone.utc),
        )
        return self._snapshots.add(snapshot)

    @staticmethod
    def _resolve_decision(
        *,
        revision_id: str,
        review_state: RevisionReviewState,
        explicit: EligibilityDecision | None,
    ) -> EligibilityDecision:
        """Determina la decisión de elegibilidad final, fail-closed."""

        if explicit is EligibilityDecision.BLOCKED:
            raise RevisionNotReleaseEligible(revision_id)

        if review_state is RevisionReviewState.NEEDS_REVIEW:
            if explicit not in _ELIGIBLE_OVERRIDES:
                raise RevisionNotReleaseEligible(revision_id)
            return explicit

        # Revisión ya procesada sin needs_review: no requiere decisión, salvo que
        # el operador pase una override explícita válida.
        if explicit in _ELIGIBLE_OVERRIDES:
            return explicit
        return EligibilityDecision.NOT_REQUIRED
