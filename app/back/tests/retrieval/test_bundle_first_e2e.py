"""End-to-end contract of the bundle-first pipeline.

ChunkBundle -> verified EmbeddingProfile -> EmbeddingRun -> sealed
EmbeddingBundle -> IndexingRun -> append_bundle_vectors -> activate_bundle ->
active RetrievalProfile -> embed_queries() with the same profile -> pgvector
query on the right target -> evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from embedding.domain.errors import (
    EmbeddingBundleInvalid,
    EmbeddingBundleStale,
    EmbeddingEngineSemanticMismatch,
    EmbeddingProfileCompatibilityNotProven,
)
from indexing.application.bundle_first.activation import (
    ActivationRequest,
    RollbackRequest,
)
from indexing.application.bundle_first.index_bundle import CreateIndexingRunRequest
from indexing.domain.errors import (
    IndexingActivationBlocked,
    IndexingIdempotencyConflict,
    IndexingTargetIncompatible,
)
from retrieval.application.retrieval_service import CreateRetrievalProfileRequest
from retrieval.domain.errors import LexicalFallbackNotAllowed, RetrievalProfileBlocked

from pipeline_fixtures import build_pipeline_stack, build_profile, build_target


SCOPE_TYPE = "chatbot"
SCOPE_ID = "sst-default"


@pytest.fixture
def stack(tmp_path: Path):
    return build_pipeline_stack(tmp_path)


def _activate(stack) -> tuple[str, str, str]:
    bundle_id = stack.run_embedding()
    run_id = stack.run_indexing(bundle_id)
    result = stack.activate_bundle.execute(
        ActivationRequest(
            run_id=run_id,
            consumer_scope_type=SCOPE_TYPE,
            consumer_scope_id=SCOPE_ID,
        )
    )
    return bundle_id, run_id, result.retrieval_profile_id


def test_e2e_devuelve_evidencia_del_target_correcto(stack) -> None:
    bundle_id, run_id, retrieval_profile_id = _activate(stack)

    retrieval_profile = stack.retrieval_profiles.get(retrieval_profile_id)
    assert retrieval_profile.is_usable is True

    evidence = stack.search.search(
        retrieval_profile=retrieval_profile,
        query="safety rules",
        top_k=3,
    )

    assert evidence, "vector retrieval returned no evidence"
    child = evidence[0]
    assert child.source == "vector"
    assert child.embedding_profile_id == stack.profile.profile_id
    assert child.corpus_version == stack.chunk_bundle.corpus_version
    assert child.embedding_bundle_id == bundle_id
    assert child.parent_node_id is not None
    assert child.page_start == 1
    assert any(item.node_id == child.parent_node_id for item in evidence)
    assert stack.indexing_runs.get(run_id).activation_status == "active"


def test_indexing_no_genera_embeddings_ni_toca_el_provider(stack, monkeypatch) -> None:
    bundle_id = stack.run_embedding()

    def _fail(*_args, **_kwargs):
        raise AssertionError("bundle-first indexing must not embed anything")

    monkeypatch.setattr(
        stack.registry,
        "resolve_document_engine",
        _fail,
    )
    monkeypatch.setattr(stack.registry, "resolve_query_engine", _fail)

    run_id = stack.run_indexing(bundle_id)

    assert stack.indexing_runs.get(run_id).status == "completed"


def test_las_filas_quedan_inactivas_hasta_la_activacion(stack) -> None:
    bundle_id = stack.run_embedding()
    stack.run_indexing(bundle_id)

    assert stack.vectors.rows, "no vector rows were appended"
    assert stack.vectors.active_rows() == []


def test_la_activacion_publica_exactamente_un_bundle_por_lane(stack) -> None:
    bundle_id, _run_id, _profile_id = _activate(stack)

    active = stack.vectors.active_rows()
    assert active
    assert {row.record.embedding_bundle_id for row in active} == {bundle_id}


def test_rechaza_indexar_un_bundle_que_no_esta_sellado(stack) -> None:
    bundle_id = stack.run_embedding()
    pending = stack.bundles.get(bundle_id).model_copy(
        update={
            "embedding_bundle_id": "embedding-bundle-pendiente",
            "status": "pending",
            "validation_status": "pending",
        }
    )
    stack.bundles._bundles[pending.embedding_bundle_id] = pending  # noqa: SLF001

    with pytest.raises(EmbeddingBundleInvalid):
        stack.create_indexing_run.execute(
            request=CreateIndexingRunRequest(
                embedding_bundle_id=pending.embedding_bundle_id
            ),
            idempotency_key="index-x",
        )


def test_rechaza_indexar_cuando_el_perfil_pierde_la_verificacion(stack) -> None:
    bundle_id = stack.run_embedding()
    stack.profiles._profiles[stack.profile.profile_id] = stack.profile.model_copy(  # noqa: SLF001
        update={"compatibility_status": "compatibility_not_proven", "document_enabled": False}
    )
    run = stack.create_indexing_run.execute(
        request=CreateIndexingRunRequest(embedding_bundle_id=bundle_id),
        idempotency_key="index-blocked",
    )

    failed = stack.indexing_executor.execute(run.run_id)

    assert failed.status == "failed"
    assert failed.summary["error_code"] == EmbeddingProfileCompatibilityNotProven.code


def test_rechaza_indexar_cuando_el_target_usa_otra_metrica(stack) -> None:
    bundle_id = stack.run_embedding()
    stack.targets._targets[stack.target.indexing_target_id] = build_target(  # noqa: SLF001
        distance_ops="vector_l2_ops"
    )

    with pytest.raises(IndexingTargetIncompatible):
        stack.create_indexing_run.execute(
            request=CreateIndexingRunRequest(embedding_bundle_id=bundle_id),
            idempotency_key="index-metric",
        )


def test_rechaza_indexar_cuando_el_contenido_fuente_cambio(stack, tmp_path) -> None:
    bundle_id = stack.run_embedding()
    child_path = tmp_path / "chunks" / "unit" / "example.child_chunks.jsonl"
    child_path.write_text(
        child_path.read_text(encoding="utf-8").replace("safety rules", "otra cosa"),
        encoding="utf-8",
    )
    run = stack.create_indexing_run.execute(
        request=CreateIndexingRunRequest(embedding_bundle_id=bundle_id),
        idempotency_key="index-stale",
    )

    failed = stack.indexing_executor.execute(run.run_id)

    assert failed.status == "failed"
    assert failed.summary["error_code"] == EmbeddingBundleStale.code


def test_devuelve_conflicto_cuando_la_key_de_indexing_se_reusa(stack) -> None:
    bundle_id = stack.run_embedding()
    stack.create_indexing_run.execute(
        request=CreateIndexingRunRequest(embedding_bundle_id=bundle_id),
        idempotency_key="index-1",
    )
    other = stack.bundles.get(bundle_id).model_copy(
        update={"embedding_bundle_id": "embedding-bundle-otro"}
    )
    stack.bundles._bundles[other.embedding_bundle_id] = other  # noqa: SLF001

    with pytest.raises(IndexingIdempotencyConflict):
        stack.create_indexing_run.execute(
            request=CreateIndexingRunRequest(embedding_bundle_id=other.embedding_bundle_id),
            idempotency_key="index-1",
        )


def test_no_activa_cuando_los_conteos_no_cuadran(stack) -> None:
    bundle_id = stack.run_embedding()
    run_id = stack.run_indexing(bundle_id)
    run = stack.indexing_runs.get(run_id)
    stack.indexing_runs.update(
        run.model_copy(update={"summary": {**run.summary, "vector_rows": 99}})
    )

    with pytest.raises(IndexingActivationBlocked):
        stack.activate_bundle.execute(
            ActivationRequest(
                run_id=run_id,
                consumer_scope_type=SCOPE_TYPE,
                consumer_scope_id=SCOPE_ID,
            )
        )
    assert stack.vectors.active_rows() == []


def test_el_rollback_reactiva_el_bundle_previo_sin_reembeber(stack, tmp_path) -> None:
    first_bundle, _run, _profile = _activate(stack)

    child_path = tmp_path / "chunks" / "unit" / "example.child_chunks.jsonl"
    child_path.write_text(
        child_path.read_text(encoding="utf-8").replace("safety rules", "reglas nuevas"),
        encoding="utf-8",
    )
    second_bundle = stack.run_embedding(idempotency_key="embed-2")
    assert second_bundle != first_bundle
    second_run = stack.run_indexing(second_bundle, idempotency_key="index-2")
    stack.activate_bundle.execute(
        ActivationRequest(
            run_id=second_run,
            consumer_scope_type=SCOPE_TYPE,
            consumer_scope_id=SCOPE_ID,
        )
    )
    assert {row.record.embedding_bundle_id for row in stack.vectors.active_rows()} == {
        second_bundle
    }

    result = stack.rollback_bundle.execute(
        RollbackRequest(
            current_embedding_bundle_id=second_bundle,
            previous_embedding_bundle_id=first_bundle,
            consumer_scope_type=SCOPE_TYPE,
            consumer_scope_id=SCOPE_ID,
        )
    )

    assert result.embedding_bundle_id == first_bundle
    assert {row.record.embedding_bundle_id for row in stack.vectors.active_rows()} == {
        first_bundle
    }


def test_la_reconciliacion_reporta_un_run_interrumpido_como_parcial(stack) -> None:
    bundle_id = stack.run_embedding()
    run = stack.create_indexing_run.execute(
        request=CreateIndexingRunRequest(embedding_bundle_id=bundle_id),
        idempotency_key="index-int",
    )
    stack.indexing_runs.claim(run.run_id)

    reconciled = stack.reconciler.reconcile()

    assert [item.run_id for item in reconciled] == [run.run_id]
    assert reconciled[0].status == "failed"
    assert reconciled[0].summary["committed_documents"] == 0


def test_bloquea_retrieval_cuando_el_perfil_no_esta_activo(stack) -> None:
    stack.run_indexing(stack.run_embedding())
    profile = stack.create_retrieval_profile.execute(
        CreateRetrievalProfileRequest(
            consumer_scope_type=SCOPE_TYPE,
            consumer_scope_id=SCOPE_ID,
            corpus_version=stack.chunk_bundle.corpus_version,
            embedding_profile_id=stack.profile.profile_id,
            indexing_target_id=stack.target.indexing_target_id,
        )
    )

    with pytest.raises(RetrievalProfileBlocked):
        stack.search.search(
            retrieval_profile=stack.retrieval_profiles.get(profile.retrieval_profile_id),
            query="safety rules",
        )


def test_no_activa_el_perfil_de_retrieval_sin_filas_activas(stack) -> None:
    stack.run_indexing(stack.run_embedding())
    profile = stack.create_retrieval_profile.execute(
        CreateRetrievalProfileRequest(
            consumer_scope_type=SCOPE_TYPE,
            consumer_scope_id=SCOPE_ID,
            corpus_version=stack.chunk_bundle.corpus_version,
            embedding_profile_id=stack.profile.profile_id,
            indexing_target_id=stack.target.indexing_target_id,
        )
    )

    with pytest.raises(RetrievalProfileBlocked):
        stack.activate_retrieval_profile.execute(profile.retrieval_profile_id)


def test_bloquea_la_consulta_cuando_el_motor_de_query_no_coincide(stack) -> None:
    _bundle, _run, retrieval_profile_id = _activate(stack)
    retrieval_profile = stack.retrieval_profiles.get(retrieval_profile_id)
    drifted = stack.profile.model_copy(update={"dimension": 16})
    stack.profiles._profiles[stack.profile.profile_id] = drifted  # noqa: SLF001

    with pytest.raises(EmbeddingEngineSemanticMismatch):
        stack.query_embedding.embed_queries(
            retrieval_profile=retrieval_profile,
            queries=["safety rules"],
        )


def test_bloquea_la_consulta_cuando_el_perfil_no_permite_queries(stack) -> None:
    _bundle, _run, retrieval_profile_id = _activate(stack)
    retrieval_profile = stack.retrieval_profiles.get(retrieval_profile_id)
    stack.profiles._profiles[stack.profile.profile_id] = stack.profile.model_copy(  # noqa: SLF001
        update={"query_enabled": False}
    )

    with pytest.raises(RetrievalProfileBlocked):
        stack.query_embedding.embed_queries(
            retrieval_profile=retrieval_profile,
            queries=["safety rules"],
        )


def test_usa_fallback_lexical_solo_cuando_la_politica_lo_permite(stack) -> None:
    _bundle, _run, retrieval_profile_id = _activate(stack)
    retrieval_profile = stack.retrieval_profiles.get(retrieval_profile_id)
    stack.registry._cache.clear()  # noqa: SLF001
    stack.registry.allow_mock = False

    evidence = stack.search.search(retrieval_profile=retrieval_profile, query="safety rules")

    assert evidence
    assert evidence[0].source == "lexical"

    strict = stack.retrieval_profiles.upsert(
        retrieval_profile.model_copy(update={"lexical_fallback_policy": "never"})
    )
    with pytest.raises(LexicalFallbackNotAllowed):
        stack.search.search(retrieval_profile=strict, query="safety rules")


def test_la_validacion_no_almacena_preguntas_reales(stack) -> None:
    _bundle, _run, retrieval_profile_id = _activate(stack)

    validation = stack.validate_retrieval.execute(retrieval_profile_id)

    assert validation.status == "passed"
    check = stack.readiness_checks.latest(
        check_kind="retrieval_readiness",
        subject_id=retrieval_profile_id,
    )
    assert check.report["query_kind"] == "synthetic_smoke"
    assert "query" not in {key for key in check.report if key != "query_kind"}


def test_no_mezcla_espacios_de_embedding_en_la_misma_lane(stack) -> None:
    bundle_id, _run, _profile_id = _activate(stack)
    other_profile = build_profile(profile_id="test-mock-v2", dimension=16)
    stack.profiles._profiles[other_profile.profile_id] = other_profile  # noqa: SLF001

    rows = stack.vector_search.search(
        vector_table=stack.target.vector_table,
        embedding_profile_id=other_profile.profile_id,
        indexing_target_id=stack.target.indexing_target_id,
        corpus_version=stack.chunk_bundle.corpus_version,
        distance_metric="cosine",
        query_embedding=[0.1] * 16,
        top_k=5,
    )

    assert rows == []
    assert {row.record.embedding_bundle_id for row in stack.vectors.active_rows()} == {
        bundle_id
    }
