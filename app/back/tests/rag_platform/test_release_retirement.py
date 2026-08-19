"""Fase 7 (Task 4): retiro formal de release (transición fail-closed a RETIRED).

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

Cubre:
- retirar una release VALIDATED o PUBLISHED la lleva a RETIRED con motivo,
- retirar una DRAFT es una transición inválida (fail-closed),
- un actor fuera de scope no puede retirar (fail-closed).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.release_retirement_service import (
    RetireRagReleaseUseCase,
)
from rag_platform.domain.errors import (
    InvalidReleaseTransition,
    PlatformAccessDenied,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import RagRelease, ReleaseState
from rag_platform.infrastructure.in_memory.release_repositories import (
    InMemoryRagReleaseRepository,
)
from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy
from api.dependencies import NullTransactionManager

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_demo")
_RELEASE = PlatformId(IdentityKind.RAG_RELEASE, "ragr_demo")


def _release(*, state: ReleaseState, manifest: str | None) -> RagRelease:
    return RagRelease(
        rag_release_id=_RELEASE,
        project_id=_PROJECT,
        rag_variant_id=PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge"),
        corpus_snapshot_id=PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1"),
        target_binding_key="primary",
        configuration_version=1,
        release_number=1,
        state=state,
        release_manifest_hash=manifest,
        created_by="op-1",
        created_at=_NOW,
    )


def _use_case(release: RagRelease) -> RetireRagReleaseUseCase:
    releases = InMemoryRagReleaseRepository()
    releases.add(release)
    return RetireRagReleaseUseCase(
        releases=releases,
        access_policy=AllowAllAccessPolicy(),
        transactions=NullTransactionManager(),
    )


def _actor() -> PlatformActor:
    return PlatformActor(actor_id="op-1", project_scope=("proj_demo",))


@pytest.mark.parametrize("state", [ReleaseState.VALIDATED, ReleaseState.PUBLISHED])
def test_retire_release_allows_validated_and_published(state) -> None:
    use_case = _use_case(_release(state=state, manifest="a" * 64))

    retired = use_case.execute(
        rag_release_id=_RELEASE, actor=_actor(), reason="deprecated_release"
    )

    assert retired.state is ReleaseState.RETIRED
    assert retired.reason == "deprecated_release"


def test_retire_draft_es_transicion_invalida() -> None:
    use_case = _use_case(_release(state=ReleaseState.DRAFT, manifest=None))

    with pytest.raises(InvalidReleaseTransition):
        use_case.execute(
            rag_release_id=_RELEASE, actor=_actor(), reason="x"
        )


def test_retire_actor_fuera_de_scope_falla_cerrado() -> None:
    use_case = _use_case(_release(state=ReleaseState.VALIDATED, manifest="a" * 64))

    with pytest.raises(PlatformAccessDenied):
        use_case.execute(
            rag_release_id=_RELEASE,
            actor=PlatformActor(actor_id="op-1", project_scope=("proj_other",)),
            reason="x",
        )
