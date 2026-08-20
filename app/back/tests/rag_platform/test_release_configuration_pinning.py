"""Fase 7 (Task 4): pin de ``configuration_version`` en la release.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

Cubre:
- el DRAFT pinnea la versión de configuración vigente y NO persiste el target
  (se deriva del binding versionado),
- build/validate usan la versión PINNEADA, no la vigente: si la configuración
  avanza tras el DRAFT, el target y el fingerprint siguen siendo los de la
  versión pinneada (sin drift).
"""

from __future__ import annotations

from datetime import datetime, timezone

from rag_platform.application.release_build_service import (
    BuildRagReleaseUseCase,
    RevisionArtifacts,
    StageResolution,
)
from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
from rag_platform.application.release_validator import ValidateRagReleaseUseCase
from rag_platform.application.platform_access import PlatformActor
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy
from api.dependencies import NullTransactionManager
from rag_platform.domain.lifecycle import (
    ReleaseState,
    compute_release_manifest_hash,
)
from rag_platform.domain.models import (
    BuildOutcome,
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
    InMemoryCurrentConfigurationVersionReader,
    InMemoryRagReleaseMembershipRepository,
    InMemoryRagReleaseRepository,
    InMemoryRagVariantReader,
    StaticConfigurationFingerprintReader,
)
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryRagBuildRunRepository,
    InMemoryTargetBindingResolver,
)

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_demo")
_VARIANT = PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
_SNAPSHOT = PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
_RELEASE = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
_RECIPE_FP = "a" * 64
_FP_V1 = "1" * 64
_FP_V2 = "2" * 64


def _variant() -> RagVariant:
    return RagVariant(
        rag_variant_id=_VARIANT,
        project_id=_PROJECT,
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local"),
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_structural"),
        embedding_profile_id="bge-m3",
        semantic_recipe_fingerprint=_RECIPE_FP,
        state=RagVariantState.ACTIVE,
        created_at=_NOW,
    )


def _revision() -> PlatformId:
    return PlatformId(IdentityKind.SOURCE_DOCUMENT_REVISION, "srev_001")


def _snapshot() -> CorpusSnapshot:
    documents = (
        CorpusSnapshotDocument(
            ordinal=0,
            source_document_revision_id=_revision(),
            eligibility_decision=EligibilityDecision.NOT_REQUIRED,
        ),
    )
    manifest = compute_corpus_manifest_hash(
        project_id=_PROJECT.value, documents=documents
    )
    return CorpusSnapshot(
        corpus_snapshot_id=_SNAPSHOT,
        project_id=_PROJECT,
        documents=documents,
        document_count=1,
        manifest_hash=manifest,
        created_at=_NOW,
    )


def _bindings() -> InMemoryTargetBindingResolver:
    # v1 y v2 mapean el mismo binding_key a targets distintos.
    resolver = InMemoryTargetBindingResolver(
        (
            ProjectIndexingTargetBinding(
                binding_key="default",
                indexing_target_id="idx_vec_old",
                embedding_profile_id="bge-m3",
            ),
        ),
        configuration_version=1,
    )
    resolver.add_binding(
        configuration_version=2,
        binding=ProjectIndexingTargetBinding(
            binding_key="default",
            indexing_target_id="idx_vec_new",
            embedding_profile_id="bge-m3",
        ),
    )
    return resolver


class _CapturingResolver:
    """Resolver de artefactos que captura el ``RagBuildContext`` derivado."""

    def __init__(self) -> None:
        self.context = None

    def resolve(self, *, context, source_document_revision_id):
        self.context = context
        rid = source_document_revision_id.value
        return RevisionArtifacts(
            normalize=StageResolution(f"norm_{rid}", BuildOutcome.BUILT),
            chunk=StageResolution(f"chunk_{rid}", BuildOutcome.BUILT),
            embed=StageResolution(f"emb_{rid}", BuildOutcome.BUILT),
            index=StageResolution(f"mat_{rid}", BuildOutcome.BUILT),
        )


def test_create_release_draft_pins_current_configuration_version() -> None:
    bindings = _bindings()
    releases = InMemoryRagReleaseRepository()
    draft = CreateRagReleaseDraftUseCase(
        variants=InMemoryRagVariantReader((_variant(),)),
        snapshots=InMemoryCorpusSnapshotReader((_snapshot(),)),
        bindings=bindings,
        releases=releases,
        configuration_versions=InMemoryCurrentConfigurationVersionReader(default=1),
        release_id_factory=lambda: _RELEASE,
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
        clock=lambda: _NOW,
    )

    release = draft.execute(
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="default",
        actor=PlatformActor(actor_id="op-1"),
    )

    assert release.configuration_version == 1
    assert release.target_binding_key == "default"
    # El target NO se persiste en la release: se deriva del binding versionado.
    assert (
        bindings.find_binding(_PROJECT, release.configuration_version, "default").indexing_target_id
        == "idx_vec_old"
    )


def test_build_and_validate_use_the_pinned_configuration_version() -> None:
    bindings = _bindings()
    releases = InMemoryRagReleaseRepository()
    current_versions = InMemoryCurrentConfigurationVersionReader(default=1)
    memberships = InMemoryRagReleaseMembershipRepository()
    variants = InMemoryRagVariantReader((_variant(),))
    snapshots = InMemoryCorpusSnapshotReader((_snapshot(),))

    draft = CreateRagReleaseDraftUseCase(
        variants=variants,
        snapshots=snapshots,
        bindings=bindings,
        releases=releases,
        configuration_versions=current_versions,
        release_id_factory=lambda: _RELEASE,
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
        clock=lambda: _NOW,
    )
    release = draft.execute(
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="default",
        actor=PlatformActor(actor_id="op-1"),
    )
    assert release.configuration_version == 1

    # La configuración avanza a la v2 (default -> idx_vec_new) tras el DRAFT.
    current_versions.set_version(_PROJECT, 2)

    resolver = _CapturingResolver()
    BuildRagReleaseUseCase(
        releases=releases,
        variants=variants,
        snapshots=snapshots,
        resolver=resolver,
        memberships=memberships,
        ledger=InMemoryRagBuildRunRepository(),
        bindings=bindings,
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
    ).execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))

    # Build derivó el target de la versión PINNEADA (v1), no de la vigente (v2).
    assert resolver.context.indexing_target_id == "idx_vec_old"

    validated = ValidateRagReleaseUseCase(
        releases=releases,
        variants=variants,
        snapshots=snapshots,
        memberships=memberships,
        configuration_fingerprints=StaticConfigurationFingerprintReader(
            by_version={(_PROJECT.value, 1): _FP_V1, (_PROJECT.value, 2): _FP_V2}
        ),
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
        clock=lambda: _NOW,
    ).execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))

    assert validated.state is ReleaseState.VALIDATED
    built_memberships = memberships.list_for_release(_RELEASE)
    expected_v1 = compute_release_manifest_hash(
        project_id=_PROJECT.value,
        rag_variant_id=_VARIANT.value,
        corpus_snapshot_id=_SNAPSHOT.value,
        corpus_manifest_hash=_snapshot().manifest_hash,
        semantic_recipe_fingerprint=_RECIPE_FP,
        configuration_fingerprint=_FP_V1,
        target_binding_key="default",
        memberships=built_memberships,
    )
    # El fingerprint congelado corresponde a la versión pinneada (v1), no a la v2.
    assert validated.release_manifest_hash == expected_v1
