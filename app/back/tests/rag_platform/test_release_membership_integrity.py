"""Fase 5: creación de DRAFT — mismo proyecto, binding permitido, sin blocked.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

Cubre `CreateRagReleaseDraftUseCase`:
- variante y snapshot deben ser del mismo proyecto (fail-closed),
- el `target_binding_key` debe estar en la allowlist y su perfil de embedding
  coincidir con la receta de la variante,
- un snapshot con revisión `blocked` no crea release,
- `release_number` es por variante (1, luego 2).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
from rag_platform.domain.errors import (
    IncompatibleTargetBinding,
    ReleaseBlockedRevision,
    ReleaseProjectMismatch,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy
from api.dependencies import NullTransactionManager
from rag_platform.domain.lifecycle import ReleaseState
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
    InMemoryCurrentConfigurationVersionReader,
    InMemoryRagReleaseRepository,
    InMemoryRagVariantReader,
)

_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_OTHER_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_beta")
_VARIANT = PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
_SNAPSHOT = PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
_NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
_RECIPE_FP = "a" * 64


class _StaticBindingResolver:
    """Allowlist mínima: un binding key hacia un perfil/target."""

    def __init__(self, binding: ProjectIndexingTargetBinding | None) -> None:
        self._binding = binding

    def find_binding(self, project_id, configuration_version, binding_key):
        if self._binding is not None and self._binding.binding_key == binding_key:
            return self._binding
        return None


def _variant(project_id: PlatformId = _PROJECT, embedding: str = "bge-m3") -> RagVariant:
    return RagVariant(
        rag_variant_id=_VARIANT,
        project_id=project_id,
        processing_profile_id=PlatformId(IdentityKind.PROCESSING_PROFILE, "pp_local"),
        chunking_profile_id=PlatformId(IdentityKind.CHUNKING_PROFILE, "cp_struct"),
        embedding_profile_id=embedding,
        semantic_recipe_fingerprint=_RECIPE_FP,
        state=RagVariantState.ACTIVE,
        created_at=_NOW,
    )


def _snapshot(
    project_id: PlatformId = _PROJECT,
    *,
    decision: EligibilityDecision = EligibilityDecision.NOT_REQUIRED,
) -> CorpusSnapshot:
    documents = (
        CorpusSnapshotDocument(
            ordinal=0,
            source_document_revision_id=PlatformId(
                IdentityKind.SOURCE_DOCUMENT_REVISION, "srev_001"
            ),
            eligibility_decision=decision,
        ),
    )
    return CorpusSnapshot(
        corpus_snapshot_id=_SNAPSHOT,
        project_id=project_id,
        documents=documents,
        document_count=1,
        manifest_hash=compute_corpus_manifest_hash(
            project_id=project_id.value, documents=documents
        ),
        created_at=_NOW,
    )


def _binding(embedding: str = "bge-m3") -> ProjectIndexingTargetBinding:
    return ProjectIndexingTargetBinding(
        binding_key="primary",
        indexing_target_id="it_bge",
        embedding_profile_id=embedding,
    )


def _use_case(
    *,
    variant: RagVariant,
    snapshot: CorpusSnapshot,
    binding: ProjectIndexingTargetBinding | None,
) -> tuple[CreateRagReleaseDraftUseCase, InMemoryRagReleaseRepository]:
    releases = InMemoryRagReleaseRepository()
    counter = {"n": 0}

    def _factory() -> PlatformId:
        counter["n"] += 1
        return PlatformId(IdentityKind.RAG_RELEASE, f"ragr_r{counter['n']}")

    use_case = CreateRagReleaseDraftUseCase(
        variants=InMemoryRagVariantReader((variant,)),
        snapshots=InMemoryCorpusSnapshotReader((snapshot,)),
        bindings=_StaticBindingResolver(binding),
        releases=releases,
        configuration_versions=InMemoryCurrentConfigurationVersionReader(),
        release_id_factory=_factory,
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
        clock=lambda: _NOW,
    )
    return use_case, releases


def test_crea_draft_cuando_todo_valido() -> None:
    use_case, _ = _use_case(
        variant=_variant(), snapshot=_snapshot(), binding=_binding()
    )

    release = use_case.execute(
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="primary",
        actor=PlatformActor(actor_id="op-1"),
    )

    assert release.state is ReleaseState.DRAFT
    assert release.project_id == _PROJECT
    assert release.release_number == 1


def test_falla_si_variante_y_snapshot_son_de_proyectos_distintos() -> None:
    use_case, _ = _use_case(
        variant=_variant(project_id=_PROJECT),
        snapshot=_snapshot(project_id=_OTHER_PROJECT),
        binding=_binding(),
    )

    with pytest.raises(ReleaseProjectMismatch):
        use_case.execute(
            rag_variant_id=_VARIANT,
            corpus_snapshot_id=_SNAPSHOT,
            target_binding_key="primary",
            actor=PlatformActor(actor_id="op-1"),
        )


def test_falla_si_binding_no_esta_en_allowlist() -> None:
    use_case, _ = _use_case(variant=_variant(), snapshot=_snapshot(), binding=None)

    with pytest.raises(IncompatibleTargetBinding):
        use_case.execute(
            rag_variant_id=_VARIANT,
            corpus_snapshot_id=_SNAPSHOT,
            target_binding_key="primary",
            actor=PlatformActor(actor_id="op-1"),
        )


def test_falla_si_binding_apunta_a_otro_perfil_de_embedding() -> None:
    use_case, _ = _use_case(
        variant=_variant(embedding="bge-m3"),
        snapshot=_snapshot(),
        binding=_binding(embedding="voyage-4"),  # no coincide con la receta
    )

    with pytest.raises(IncompatibleTargetBinding):
        use_case.execute(
            rag_variant_id=_VARIANT,
            corpus_snapshot_id=_SNAPSHOT,
            target_binding_key="primary",
            actor=PlatformActor(actor_id="op-1"),
        )


def test_falla_si_snapshot_tiene_revision_blocked() -> None:
    use_case, _ = _use_case(
        variant=_variant(),
        snapshot=_snapshot(decision=EligibilityDecision.BLOCKED),
        binding=_binding(),
    )

    with pytest.raises(ReleaseBlockedRevision):
        use_case.execute(
            rag_variant_id=_VARIANT,
            corpus_snapshot_id=_SNAPSHOT,
            target_binding_key="primary",
            actor=PlatformActor(actor_id="op-1"),
        )


def test_release_number_incrementa_por_variante() -> None:
    use_case, _ = _use_case(
        variant=_variant(), snapshot=_snapshot(), binding=_binding()
    )

    first = use_case.execute(
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="primary",
        actor=PlatformActor(actor_id="op-1"),
    )
    second = use_case.execute(
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="primary",
        actor=PlatformActor(actor_id="op-1"),
    )

    assert first.release_number == 1
    assert second.release_number == 2
