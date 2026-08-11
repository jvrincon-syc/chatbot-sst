"""Fase 4: lifecycle inmutable de materialización de vectores (ADR-007 §3).

Una materialización sellada es inmutable: rechaza mutación y no se reabre para
escritura. La validación transaccional falla cerrado (conteos, owner, dimensión,
métrica) y deja la materialización ``FAILED`` observable.
"""

from __future__ import annotations

import pytest

from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
from rag_platform.domain.errors import (
    MaterializationSealed,
    MaterializationValidationFailed,
    NodeProjectMismatch,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import MaterializationStatus
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryIndexingMaterializationRepository,
)


_PROJECT_A = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_PROJECT_B = PlatformId(IdentityKind.PROJECT, "proj_beta")
_CHECKSUM = "a" * 64
_OTHER_CHECKSUM = "b" * 64
_STORAGE_SCHEMA = "idx-materialization-v1"


def _use_case() -> tuple[
    MaterializeVectorsUseCase, InMemoryIndexingMaterializationRepository
]:
    repo = InMemoryIndexingMaterializationRepository()
    return MaterializeVectorsUseCase(repository=repo), repo


def _materialize(use_case: MaterializeVectorsUseCase, **overrides: object):
    payload: dict[str, object] = {
        "requested_project_id": _PROJECT_A,
        "bundle_project_id": _PROJECT_A,
        "embedding_bundle_id": "eb_01",
        "indexing_target_id": "it_bge",
        "storage_schema_version": _STORAGE_SCHEMA,
        "canonical_checksum": _CHECKSUM,
        "parent_node_count": 1,
        "child_node_count": 2,
        "vector_count": 2,
        "bundle_dimension": 1024,
        "target_dimension": 1024,
        "bundle_metric": "cosine",
        "target_metric": "cosine",
    }
    payload.update(overrides)
    return use_case.materialize(**payload)  # type: ignore[arg-type]


def test_sella_materializacion_cuando_todo_cuadra() -> None:
    use_case, _ = _use_case()

    materialization = _materialize(use_case)

    assert materialization.status is MaterializationStatus.SEALED
    assert materialization.canonical_checksum == _CHECKSUM
    assert materialization.vector_count == 2
    assert materialization.sealed_at is not None


def test_reseal_idempotente_cuando_mismo_checksum() -> None:
    use_case, _ = _use_case()
    first = _materialize(use_case)

    second = _materialize(use_case)

    assert second.materialization_id == first.materialization_id
    assert second.status is MaterializationStatus.SEALED


def test_sealed_materialization_rejects_mutation() -> None:
    use_case, _ = _use_case()
    _materialize(use_case)

    with pytest.raises(MaterializationSealed):
        _materialize(use_case, canonical_checksum=_OTHER_CHECKSUM)


def test_begin_writing_no_reabre_una_materializacion_sellada() -> None:
    use_case, repo = _use_case()
    _materialize(use_case)

    with pytest.raises(MaterializationSealed):
        repo.begin_writing(
            project_id=_PROJECT_A,
            embedding_bundle_id="eb_01",
            indexing_target_id="it_bge",
            storage_schema_version=_STORAGE_SCHEMA,
        )


def test_falla_cerrado_cuando_conteos_no_cuadran() -> None:
    use_case, repo = _use_case()

    with pytest.raises(MaterializationValidationFailed):
        _materialize(use_case, vector_count=5, child_node_count=2)

    # La materialización queda FAILED (observable), nunca sellada a medias.
    assert repo.find_sealed(
        project_id=_PROJECT_A,
        embedding_bundle_id="eb_01",
        indexing_target_id="it_bge",
        storage_schema_version=_STORAGE_SCHEMA,
    ) is None


def test_falla_cerrado_cuando_dimension_no_coincide() -> None:
    use_case, _ = _use_case()

    with pytest.raises(MaterializationValidationFailed):
        _materialize(use_case, bundle_dimension=768, target_dimension=1024)


def test_falla_cerrado_cuando_metrica_no_coincide() -> None:
    use_case, _ = _use_case()

    with pytest.raises(MaterializationValidationFailed):
        _materialize(use_case, bundle_metric="l2", target_metric="cosine")


def test_falla_cerrado_cuando_owner_de_proyecto_no_coincide() -> None:
    use_case, _ = _use_case()

    with pytest.raises(NodeProjectMismatch):
        _materialize(use_case, bundle_project_id=_PROJECT_B)


def test_materializacion_marcada_failed_es_reintentables() -> None:
    use_case, repo = _use_case()
    with pytest.raises(MaterializationValidationFailed):
        _materialize(use_case, vector_count=9, child_node_count=2)

    # Un reintento correcto sella normalmente (la fila FAILED no bloquea).
    sealed = _materialize(use_case)
    assert sealed.status is MaterializationStatus.SEALED
