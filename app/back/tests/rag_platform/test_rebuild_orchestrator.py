"""Bloque G (Fase 4): rebuild limpio platform-only hasta materialización sellada.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite; se ejecuta en la
máquina de gates reales (2026-08-11).

Verifica el composition root:
- deriva ``project_id`` del build context validado (nunca del payload),
- encadena indexado bundle-first + materialización sellada,
- deja los vectores inactivos (no activa),
- falla cerrado si el bundle pertenece a otro proyecto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_platform.application.rebuild_orchestrator import (
    PlatformBuildContext,
    RebuildPlatformArtifactsUseCase,
)
from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
from rag_platform.domain.errors import NodeProjectMismatch
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import MaterializationStatus
from rag_platform.infrastructure.in_memory.repositories import (
    InMemoryIndexingMaterializationRepository,
)

from pipeline_fixtures import build_pipeline_stack

_PROJECT = "proj_alpha"
_STORAGE_SCHEMA = "idx-materialization-v1"


def _platform_stack(tmp_path: Path):
    """Pipeline stack whose chunk bundle is owned by ``_PROJECT``."""

    stack = build_pipeline_stack(tmp_path)
    project_bundle = stack.chunk_bundle.model_copy(update={"project_id": _PROJECT})
    stack.chunk_bundle = project_bundle
    stack.chunk_bundles.ensure_registered(project_bundle)
    return stack


def _use_case(stack) -> tuple[
    RebuildPlatformArtifactsUseCase, InMemoryIndexingMaterializationRepository
]:
    materialization_repo = InMemoryIndexingMaterializationRepository()
    use_case = RebuildPlatformArtifactsUseCase(
        create_indexing_run=stack.create_indexing_run,
        indexing_executor=stack.indexing_executor,
        run_documents=stack.run_documents,
        bundles=stack.bundles,
        profiles=stack.profiles,
        materialize=MaterializeVectorsUseCase(repository=materialization_repo),
        storage_schema_version=_STORAGE_SCHEMA,
    )
    return use_case, materialization_repo


def _rebuild(use_case, stack, *, project_id: str = _PROJECT, embedding_bundle_id=None):
    embedding_bundle_id = embedding_bundle_id or stack.run_embedding()
    return use_case.execute(
        context=PlatformBuildContext(
            project_id=PlatformId(IdentityKind.PROJECT, project_id)
        ),
        embedding_bundle_id=embedding_bundle_id,
    )


def test_rebuild_sella_materializacion_del_proyecto(tmp_path: Path) -> None:
    stack = _platform_stack(tmp_path)
    use_case, _ = _use_case(stack)

    result = _rebuild(use_case, stack)

    assert result.materialization.status is MaterializationStatus.SEALED
    # Checksum canónico derivado server-side del bundle (64 hex determinista).
    assert len(result.materialization.canonical_checksum) == 64
    int(result.materialization.canonical_checksum, 16)
    # vector_count == child_node_count (cada child aporta un vector).
    assert result.materialization.vector_count == result.materialization.child_node_count
    assert result.materialization.child_node_count > 0


def test_rebuild_deja_vectores_inactivos(tmp_path: Path) -> None:
    stack = _platform_stack(tmp_path)
    use_case, _ = _use_case(stack)

    _rebuild(use_case, stack)

    # ADR-007 §8: el rebuild no activa nada.
    assert stack.vectors.rows
    assert all(not row.is_active for row in stack.vectors.rows.values())
    assert {row.record.project_id for row in stack.vectors.rows.values()} == {_PROJECT}


def test_rebuild_falla_cerrado_si_bundle_es_de_otro_proyecto(tmp_path: Path) -> None:
    stack = _platform_stack(tmp_path)
    use_case, repo = _use_case(stack)
    embedding_bundle_id = stack.run_embedding()

    # El bundle es de _PROJECT; pedir la materialización bajo otro proyecto falla.
    with pytest.raises(NodeProjectMismatch):
        _rebuild(
            use_case,
            stack,
            project_id="proj_beta",
            embedding_bundle_id=embedding_bundle_id,
        )

    # La materialización queda observable como FAILED, nunca sellada a medias.
    sealed = repo.find_sealed(
        project_id=PlatformId(IdentityKind.PROJECT, "proj_beta"),
        embedding_bundle_id=embedding_bundle_id,
        indexing_target_id=stack.target.indexing_target_id,
        storage_schema_version=_STORAGE_SCHEMA,
    )
    assert sealed is None


def test_build_context_rechaza_kind_equivocado() -> None:
    # Fail-closed: una variante donde se espera un proyecto no se cablea.
    with pytest.raises(ValueError):
        PlatformBuildContext(project_id=PlatformId(IdentityKind.RAG_VARIANT, "ragv_x"))
