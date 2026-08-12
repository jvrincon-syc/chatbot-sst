"""Fase 5: planner de build — reuso por identidad, membresías y ledger.

Cubre `BuildRagReleaseUseCase`:
- recorre las revisiones del snapshot y crea una membresía por revisión,
- registra cada etapa (normalize/chunk/embed/index) en el ledger con su outcome,
- exit criteria incremental: r002 (56 docs) reutiliza lo de r001 (55) y solo
  construye el documento nuevo; r001 no ve el documento 56.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rag_platform.application.release_build_service import (
    BuildRagReleaseUseCase,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import RagRelease, ReleaseState
from rag_platform.domain.models import (
    CorpusSnapshot,
    CorpusSnapshotDocument,
    EligibilityDecision,
    ProjectIndexingTargetBinding,
    RagVariant,
    RagVariantState,
    compute_corpus_manifest_hash,
)
from rag_platform.infrastructure.in_memory.release_repositories import (
    InMemoryCorpusSnapshotReader,
    InMemoryRagReleaseMembershipRepository,
    InMemoryRagReleaseRepository,
    InMemoryRagVariantReader,
)
from rag_platform.infrastructure.in_memory.release_build_resolver import (
    InMemoryRevisionArtifactResolver,
)
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryRagBuildRunRepository,
)

_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_VARIANT = PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
_SNAPSHOT = PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
_NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
_RECIPE_FP = "a" * 64


class _StaticBindingResolver:
    def find_binding(self, project_id, binding_key):
        return ProjectIndexingTargetBinding(
            binding_key=binding_key,
            indexing_target_id="it_bge",
            embedding_profile_id="bge-m3",
        )


def _variant() -> RagVariant:
    return RagVariant(
        rag_variant_id=_VARIANT,
        project_id=_PROJECT,
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local"),
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_struct"),
        embedding_profile_id="bge-m3",
        semantic_recipe_fingerprint=_RECIPE_FP,
        state=RagVariantState.ACTIVE,
        created_at=_NOW,
    )


def _snapshot(snapshot_id: PlatformId, *, count: int) -> CorpusSnapshot:
    documents = tuple(
        CorpusSnapshotDocument(
            ordinal=i,
            source_document_revision_id=PlatformId(
                IdentityKind.SOURCE_DOCUMENT_REVISION, f"srev_{i:03d}"
            ),
            eligibility_decision=EligibilityDecision.NOT_REQUIRED,
        )
        for i in range(count)
    )
    return CorpusSnapshot(
        corpus_snapshot_id=snapshot_id,
        project_id=_PROJECT,
        documents=documents,
        document_count=count,
        manifest_hash=compute_corpus_manifest_hash(
            project_id=_PROJECT.value, documents=documents
        ),
        created_at=_NOW,
    )


def _release(release_id: PlatformId, snapshot_id: PlatformId) -> RagRelease:
    return RagRelease(
        rag_release_id=release_id,
        project_id=_PROJECT,
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=snapshot_id,
        target_binding_key="primary",
        release_number=1,
        state=ReleaseState.DRAFT,
        created_by="op-1",
        created_at=_NOW,
    )


def _build(
    *,
    release: RagRelease,
    snapshot: CorpusSnapshot,
    resolver: InMemoryRevisionArtifactResolver,
    ledger: InMemoryRagBuildRunRepository | None = None,
) -> tuple[
    BuildRagReleaseUseCase,
    InMemoryRagReleaseMembershipRepository,
    InMemoryRagBuildRunRepository,
]:
    releases = InMemoryRagReleaseRepository()
    releases.add(release)
    memberships = InMemoryRagReleaseMembershipRepository()
    ledger = ledger or InMemoryRagBuildRunRepository()
    use_case = BuildRagReleaseUseCase(
        releases=releases,
        variants=InMemoryRagVariantReader((_variant(),)),
        snapshots=InMemoryCorpusSnapshotReader((snapshot,)),
        resolver=resolver,
        memberships=memberships,
        ledger=ledger,
        bindings=_StaticBindingResolver(),
    )
    return use_case, memberships, ledger


def test_build_crea_una_membresia_por_revision_y_audita_cada_etapa() -> None:
    release_id = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
    snapshot = _snapshot(_SNAPSHOT, count=2)
    resolver = InMemoryRevisionArtifactResolver()
    use_case, memberships, ledger = _build(
        release=_release(release_id, _SNAPSHOT), snapshot=snapshot, resolver=resolver
    )

    report = use_case.execute(rag_release_id=release_id, actor_id="op-1")

    assert report.revisions_built == 2
    assert len(memberships.list_for_release(release_id)) == 2
    # 2 revisiones x 4 etapas = 8 pasos auditados.
    assert len(ledger.steps_for(release_id)) == 8
    assert report.built_stages == 8
    assert report.reused_stages == 0


def test_build_incremental_reutiliza_lo_previo_y_solo_construye_lo_nuevo() -> None:
    # r001 = 55 docs (srev_000..srev_054); r002 = 56 docs (añade srev_055).
    release1 = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
    release2 = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r2")
    snapshot1 = _snapshot(_SNAPSHOT, count=55)
    snapshot2 = _snapshot(
        PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s2"), count=56
    )
    resolver = InMemoryRevisionArtifactResolver()
    use_case1, _, ledger1 = _build(
        release=_release(release1, _SNAPSHOT), snapshot=snapshot1, resolver=resolver
    )
    use_case1.execute(rag_release_id=release1, actor_id="op-1")
    use_case, memberships, ledger = _build(
        release=_release(release2, snapshot2.corpus_snapshot_id),
        snapshot=snapshot2,
        resolver=resolver,
    )

    report = use_case.execute(rag_release_id=release2, actor_id="op-1")

    assert report.revisions_built == 56
    assert len(memberships.list_for_release(release2)) == 56
    # 55 revisiones reutilizadas x 4 + 1 nueva x 4 = 220 reused, 4 built.
    assert report.reused_stages == 55 * 4
    assert report.built_stages == 4
    assert len(ledger1.steps_for(release1)) == 55 * 4
    assert len(ledger.steps_for(release2)) == 56 * 4


def test_r001_no_ve_el_documento_56() -> None:
    release1 = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
    snapshot1 = _snapshot(_SNAPSHOT, count=55)
    resolver = InMemoryRevisionArtifactResolver()
    use_case, memberships, _ = _build(
        release=_release(release1, _SNAPSHOT), snapshot=snapshot1, resolver=resolver
    )

    use_case.execute(rag_release_id=release1, actor_id="op-1")

    revisions = {
        member.source_document_revision_id.value
        for member in memberships.list_for_release(release1)
    }
    assert "srev_055" not in revisions
    assert len(revisions) == 55
