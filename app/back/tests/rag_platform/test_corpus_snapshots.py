"""Fase 2: corpus snapshots deterministas y elegibilidad fail-closed."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.corpus_snapshot_service import (
    CreateCorpusSnapshotUseCase,
)
from rag_platform.domain.errors import (
    RevisionNotReleaseEligible,
    RevisionProjectMismatch,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    EligibilityDecision,
    RevisionReviewState,
    SourceDocument,
    SourceDocumentRevision,
)
from rag_platform.infrastructure.in_memory.repositories import (
    AllowAllAccessPolicy,
    InMemoryCorpusSnapshotRepository,
    InMemorySourceDocumentRepository,
)


_PROJECT = "sst-general"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_revision(
    documents: InMemorySourceDocumentRepository,
    *,
    revision_id: str,
    project: str = _PROJECT,
    review_state: RevisionReviewState = RevisionReviewState.PROCESSED,
) -> str:
    project_pid = PlatformId(IdentityKind.PROJECT, f"proj_{project}")
    logical = PlatformId(IdentityKind.SOURCE_DOCUMENT, f"sdoc_{revision_id}")
    documents.upsert_document(
        SourceDocument(
            logical_document_id=logical,
            project_id=project_pid,
            source_relpath=f"manual/{revision_id}.pdf",
            created_at=_now(),
        )
    )
    documents.add_revision(
        SourceDocumentRevision(
            source_document_revision_id=PlatformId(
                IdentityKind.SOURCE_DOCUMENT_REVISION, f"srev_{revision_id}"
            ),
            logical_document_id=logical,
            project_id=project_pid,
            source_relpath=f"manual/{revision_id}.pdf",
            raw_content_hash=f"hash-{revision_id}",
            file_size=100,
            uploaded_by="op",
            uploaded_at=_now(),
            review_state=review_state,
        )
    )
    return f"srev_{revision_id}"


def _use_case(
    documents: InMemorySourceDocumentRepository,
) -> tuple[CreateCorpusSnapshotUseCase, InMemoryCorpusSnapshotRepository]:
    snapshots = InMemoryCorpusSnapshotRepository()
    use_case = CreateCorpusSnapshotUseCase(
        snapshots=snapshots,
        documents=documents,
        access_policy=AllowAllAccessPolicy(),
    )
    return use_case, snapshots


def test_mismo_input_produce_mismo_manifest_hash() -> None:
    documents = InMemorySourceDocumentRepository()
    a = _seed_revision(documents, revision_id="a")
    b = _seed_revision(documents, revision_id="b")
    use_case, snapshots = _use_case(documents)

    first = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b], actor_id="op"
    )
    # Idempotencia: mismo conjunto ordenado => mismo snapshot (mismo hash).
    second = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b], actor_id="op"
    )
    assert first.manifest_hash == second.manifest_hash
    assert first.corpus_snapshot_id == second.corpus_snapshot_id
    assert first.document_count == 2


def test_orden_distinto_produce_hash_distinto() -> None:
    documents = InMemorySourceDocumentRepository()
    a = _seed_revision(documents, revision_id="a")
    b = _seed_revision(documents, revision_id="b")
    use_case, _ = _use_case(documents)

    ab = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b], actor_id="op"
    )
    ba = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[b, a], actor_id="op"
    )
    assert ab.manifest_hash != ba.manifest_hash


def test_cambio_material_de_seleccion_produce_snapshot_nuevo() -> None:
    documents = InMemorySourceDocumentRepository()
    a = _seed_revision(documents, revision_id="a")
    b = _seed_revision(documents, revision_id="b")
    c = _seed_revision(documents, revision_id="c")
    use_case, _ = _use_case(documents)

    ab = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b], actor_id="op"
    )
    abc = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b, c], actor_id="op"
    )
    assert ab.manifest_hash != abc.manifest_hash
    assert ab.corpus_snapshot_id != abc.corpus_snapshot_id


def test_snapshot_reconstruible_solo_con_sus_rows() -> None:
    from rag_platform.domain.models import compute_corpus_manifest_hash

    documents = InMemorySourceDocumentRepository()
    a = _seed_revision(documents, revision_id="a")
    b = _seed_revision(documents, revision_id="b")
    use_case, _ = _use_case(documents)

    snapshot = use_case.execute(
        project_id=_PROJECT, document_revision_ids=[a, b], actor_id="op"
    )
    # Recomputar el hash solo con las membresías persistidas debe coincidir.
    recomputed = compute_corpus_manifest_hash(
        project_id=snapshot.project_id.value, documents=snapshot.documents
    )
    assert recomputed == snapshot.manifest_hash


def test_needs_review_sin_decision_rechaza_fail_closed() -> None:
    documents = InMemorySourceDocumentRepository()
    r = _seed_revision(
        documents, revision_id="r", review_state=RevisionReviewState.NEEDS_REVIEW
    )
    use_case, _ = _use_case(documents)

    with pytest.raises(RevisionNotReleaseEligible):
        use_case.execute(
            project_id=_PROJECT, document_revision_ids=[r], actor_id="op"
        )


def test_needs_review_con_approved_after_review_entra() -> None:
    documents = InMemorySourceDocumentRepository()
    r = _seed_revision(
        documents, revision_id="r", review_state=RevisionReviewState.NEEDS_REVIEW
    )
    use_case, _ = _use_case(documents)

    snapshot = use_case.execute(
        project_id=_PROJECT,
        document_revision_ids=[r],
        actor_id="op",
        eligibility_decisions={r: EligibilityDecision.APPROVED_AFTER_REVIEW},
    )
    assert snapshot.document_count == 1
    assert (
        snapshot.documents[0].eligibility_decision
        is EligibilityDecision.APPROVED_AFTER_REVIEW
    )


def test_blocked_rechaza_fail_closed() -> None:
    documents = InMemorySourceDocumentRepository()
    r = _seed_revision(documents, revision_id="r")
    use_case, _ = _use_case(documents)

    with pytest.raises(RevisionNotReleaseEligible):
        use_case.execute(
            project_id=_PROJECT,
            document_revision_ids=[r],
            actor_id="op",
            eligibility_decisions={r: EligibilityDecision.BLOCKED},
        )


def test_revision_de_otro_proyecto_rechaza() -> None:
    documents = InMemorySourceDocumentRepository()
    foreign = _seed_revision(documents, revision_id="f", project="calidad-interna")
    use_case, _ = _use_case(documents)

    with pytest.raises(RevisionProjectMismatch):
        use_case.execute(
            project_id=_PROJECT, document_revision_ids=[foreign], actor_id="op"
        )
