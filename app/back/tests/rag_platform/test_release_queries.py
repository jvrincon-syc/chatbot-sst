"""Fase 7 (Task 4): lecturas de release (get + list por proyecto).

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rag_platform.application.release_query_service import (
    GetReleaseUseCase,
    ListProjectReleasesUseCase,
)
from rag_platform.domain.errors import RagReleaseNotFound
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import RagRelease, ReleaseState
from rag_platform.infrastructure.in_memory.release_repositories import (
    InMemoryRagReleaseRepository,
)

_NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_demo")
_OTHER = PlatformId(IdentityKind.PROJECT, "proj_other")


def _release(release_id: str, project: PlatformId, number: int) -> RagRelease:
    return RagRelease(
        rag_release_id=PlatformId(IdentityKind.RAG_RELEASE, release_id),
        project_id=project,
        rag_variant_id=PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge"),
        corpus_snapshot_id=PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1"),
        target_binding_key="primary",
        configuration_version=1,
        release_number=number,
        state=ReleaseState.DRAFT,
        created_by="op-1",
        created_at=_NOW,
    )


def _repo() -> InMemoryRagReleaseRepository:
    repo = InMemoryRagReleaseRepository()
    repo.add(_release("ragr_a", _PROJECT, 1))
    repo.add(_release("ragr_b", _PROJECT, 2))
    repo.add(_release("ragr_z", _OTHER, 1))
    return repo


def test_get_release_devuelve_la_release_por_id() -> None:
    release = GetReleaseUseCase(releases=_repo()).execute(
        PlatformId(IdentityKind.RAG_RELEASE, "ragr_a")
    )

    assert release.rag_release_id.value == "ragr_a"


def test_get_release_inexistente_falla_cerrado() -> None:
    with pytest.raises(RagReleaseNotFound):
        GetReleaseUseCase(releases=_repo()).execute(
            PlatformId(IdentityKind.RAG_RELEASE, "ragr_missing")
        )


def test_list_project_releases_solo_las_del_proyecto() -> None:
    releases = ListProjectReleasesUseCase(releases=_repo()).execute(_PROJECT)

    assert {r.rag_release_id.value for r in releases} == {"ragr_a", "ragr_b"}
