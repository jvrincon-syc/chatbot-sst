"""Fase 5: lifecycle de release, manifiesto determinista y validación.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite; se ejecuta en la
máquina de gates reales.

Cubre:
- transiciones válidas/ inválidas del lifecycle (`ensure_transition_allowed`),
- `release_manifest_hash` determinista y reconstruible,
- validación: congela el manifiesto, exige completitud, rechaza `blocked`,
- una release validada no se re-valida en sitio (manifiesto congelado).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.release_validator import ValidateRagReleaseUseCase
from rag_platform.domain.errors import (
    InvalidReleaseTransition,
    ReleaseBlockedRevision,
    ReleaseManifestFrozen,
    ReleaseNotComplete,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    RagReleaseMembership,
    ReleaseState,
    compute_release_manifest_hash,
    ensure_transition_allowed,
    next_release_number,
)
from rag_platform.domain.models import (
    CorpusSnapshot,
    CorpusSnapshotDocument,
    EligibilityDecision,
    RagVariant,
    RagVariantState,
    compute_corpus_manifest_hash,
)
from rag_platform.infrastructure.in_memory.release_repositories import (
    InMemoryCorpusSnapshotReader,
    InMemoryRagReleaseMembershipRepository,
    InMemoryRagReleaseRepository,
    InMemoryRagVariantReader,
    StaticConfigurationFingerprintReader,
)

_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_VARIANT = PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
_SNAPSHOT = PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
_RELEASE = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
_RECIPE_FP = "a" * 64
_CONFIG_FP = "c" * 64
_NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _revision(n: int) -> PlatformId:
    return PlatformId(IdentityKind.SOURCE_DOCUMENT_REVISION, f"srev_{n:03d}")


def _snapshot(*, decisions: dict[int, EligibilityDecision]) -> CorpusSnapshot:
    documents = tuple(
        CorpusSnapshotDocument(
            ordinal=i,
            source_document_revision_id=_revision(i),
            eligibility_decision=decisions.get(i, EligibilityDecision.NOT_REQUIRED),
        )
        for i in range(len(decisions))
    )
    manifest = compute_corpus_manifest_hash(
        project_id=_PROJECT.value, documents=documents
    )
    return CorpusSnapshot(
        corpus_snapshot_id=_SNAPSHOT,
        project_id=_PROJECT,
        documents=documents,
        document_count=len(documents),
        manifest_hash=manifest,
        created_at=_NOW,
    )


def _membership(i: int) -> RagReleaseMembership:
    return RagReleaseMembership(
        rag_release_id=_RELEASE,
        project_id=_PROJECT,
        ordinal=i,
        source_document_revision_id=_revision(i),
        normalized_document_id=f"norm_{i}",
        chunk_bundle_id=f"chunk_{i}",
        embedding_bundle_id=f"emb_{i}",
        materialization_id=f"mat_{i}",
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


def _draft_release() -> RagRelease:
    return RagRelease(
        rag_release_id=_RELEASE,
        project_id=_PROJECT,
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="primary",
        release_number=1,
        state=ReleaseState.DRAFT,
        created_by="op-1",
        created_at=_NOW,
    )


# --------------------------------------------------------------------------- #
# Lifecycle puro                                                              #
# --------------------------------------------------------------------------- #


def test_transiciones_validas() -> None:
    ensure_transition_allowed(current=ReleaseState.DRAFT, target=ReleaseState.VALIDATED)
    ensure_transition_allowed(
        current=ReleaseState.VALIDATED, target=ReleaseState.PUBLISHED
    )
    ensure_transition_allowed(
        current=ReleaseState.PUBLISHED, target=ReleaseState.RETIRED
    )


@pytest.mark.parametrize(
    "current, target",
    [
        (ReleaseState.DRAFT, ReleaseState.PUBLISHED),  # no salta validación
        (ReleaseState.PUBLISHED, ReleaseState.DRAFT),  # no retrocede
        (ReleaseState.RETIRED, ReleaseState.PUBLISHED),  # terminal
        (ReleaseState.FAILED, ReleaseState.VALIDATED),  # terminal
    ],
)
def test_transiciones_invalidas(current, target) -> None:
    with pytest.raises(InvalidReleaseTransition):
        ensure_transition_allowed(current=current, target=target)


def test_release_number_por_variante() -> None:
    assert next_release_number(existing_numbers=[]) == 1
    assert next_release_number(existing_numbers=[1, 2]) == 3


def test_manifest_hash_determinista_y_reconstruible() -> None:
    members = [_membership(0), _membership(1)]
    kwargs = dict(
        project_id=_PROJECT.value,
        rag_variant_id=_VARIANT.value,
        corpus_snapshot_id=_SNAPSHOT.value,
        corpus_manifest_hash="b" * 64,
        semantic_recipe_fingerprint=_RECIPE_FP,
        configuration_fingerprint=_CONFIG_FP,
        target_binding_key="primary",
    )
    first = compute_release_manifest_hash(memberships=members, **kwargs)
    # Reordenar la entrada no cambia el hash (se ordena por ordinal).
    second = compute_release_manifest_hash(memberships=list(reversed(members)), **kwargs)
    assert first == second
    # Cambiar una membresía sí cambia el hash.
    changed = compute_release_manifest_hash(
        memberships=[_membership(0), _membership(2)], **kwargs
    )
    assert changed != first


# --------------------------------------------------------------------------- #
# Validación                                                                  #
# --------------------------------------------------------------------------- #


def _validator(
    *, release: RagRelease, snapshot: CorpusSnapshot, memberships
) -> tuple[ValidateRagReleaseUseCase, InMemoryRagReleaseRepository]:
    releases = InMemoryRagReleaseRepository()
    releases.add(release)
    membership_repo = InMemoryRagReleaseMembershipRepository()
    for member in memberships:
        membership_repo.add(member)
    variant_reader = InMemoryRagVariantReader((_variant(),))

    use_case = ValidateRagReleaseUseCase(
        releases=releases,
        variants=variant_reader,
        snapshots=InMemoryCorpusSnapshotReader((snapshot,)),
        memberships=membership_repo,
        configuration_fingerprints=StaticConfigurationFingerprintReader(
            {_PROJECT.value: _CONFIG_FP}
        ),
        clock=lambda: _NOW,
    )
    return use_case, releases


def test_validar_congela_manifiesto_y_pasa_a_validated() -> None:
    snapshot = _snapshot(decisions={0: EligibilityDecision.NOT_REQUIRED})
    use_case, releases = _validator(
        release=_draft_release(), snapshot=snapshot, memberships=[_membership(0)]
    )

    result = use_case.execute(rag_release_id=_RELEASE, actor_id="op-1")

    assert result.state is ReleaseState.VALIDATED
    assert result.release_manifest_hash is not None
    assert result.validated_at == _NOW


def test_validar_falla_si_falta_una_membresia() -> None:
    snapshot = _snapshot(
        decisions={
            0: EligibilityDecision.NOT_REQUIRED,
            1: EligibilityDecision.NOT_REQUIRED,
        }
    )
    use_case, _ = _validator(
        release=_draft_release(), snapshot=snapshot, memberships=[_membership(0)]
    )

    with pytest.raises(ReleaseNotComplete):
        use_case.execute(rag_release_id=_RELEASE, actor_id="op-1")


def test_validar_rechaza_revision_blocked() -> None:
    snapshot = _snapshot(decisions={0: EligibilityDecision.BLOCKED})
    use_case, _ = _validator(
        release=_draft_release(), snapshot=snapshot, memberships=[_membership(0)]
    )

    with pytest.raises(ReleaseBlockedRevision):
        use_case.execute(rag_release_id=_RELEASE, actor_id="op-1")


def test_release_validada_no_se_revalida_en_sitio() -> None:
    snapshot = _snapshot(decisions={0: EligibilityDecision.NOT_REQUIRED})
    frozen = _draft_release().model_copy(
        update={"state": ReleaseState.VALIDATED, "release_manifest_hash": "d" * 64}
    )
    use_case, _ = _validator(
        release=frozen, snapshot=snapshot, memberships=[_membership(0)]
    )

    with pytest.raises(ReleaseManifestFrozen):
        use_case.execute(rag_release_id=_RELEASE, actor_id="op-1")
