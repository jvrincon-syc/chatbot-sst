from __future__ import annotations

import json
from pathlib import Path

import pytest

from embedding.application.bundle_builder import EmbeddingIndexingReadinessEvaluator
from embedding.application.run_service import CreateEmbeddingRunRequest
from embedding.domain.errors import (
    ChunkBundleNotFound,
    EmbeddingBundleInvalid,
    EmbeddingProfileCompatibilityNotProven,
    IdempotencyConflict,
)
from embedding.infrastructure.in_memory.repositories import (
    InMemoryEmbeddingProfileRepository,
)

from pipeline_fixtures import build_profile, build_target


def _request(harness) -> CreateEmbeddingRunRequest:
    return CreateEmbeddingRunRequest(
        chunk_bundle_id=harness.chunk_bundle.chunk_bundle_id,
        profile_id=harness.profile.profile_id,
    )


def test_crea_y_ejecuta_un_run_cuando_el_perfil_esta_verificado(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    assert run.status == "pending"

    completed = harness.executor.execute(run.embedding_run_id)

    assert completed.status == "completed"
    assert completed.produced_embedding_bundle_id is not None
    assert completed.summary["embedded_children"] == harness.chunk_bundle.child_count
    bundle = harness.bundles.get(completed.produced_embedding_bundle_id)
    assert bundle.is_sealed is True
    assert bundle.vector_count == harness.chunk_bundle.child_count
    assert bundle.vector_dtype == "float32"


def test_devuelve_el_mismo_run_cuando_la_key_y_el_payload_se_repiten(harness) -> None:
    first = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    second = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")

    assert first.embedding_run_id == second.embedding_run_id


def test_devuelve_conflicto_cuando_la_key_se_reusa_con_otro_payload(harness) -> None:
    harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    other_profile = build_profile(profile_id="test-mock-v2")
    harness.profiles._profiles[other_profile.profile_id] = other_profile  # noqa: SLF001

    with pytest.raises(IdempotencyConflict):
        harness.create_run.execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id=harness.chunk_bundle.chunk_bundle_id,
                profile_id=other_profile.profile_id,
            ),
            idempotency_key="key-1",
        )


def test_rechaza_la_creacion_cuando_el_perfil_es_legacy_no_verificado(harness) -> None:
    blocked = build_profile(
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
    )
    harness.profiles._profiles[blocked.profile_id] = blocked  # noqa: SLF001

    with pytest.raises(EmbeddingProfileCompatibilityNotProven):
        harness.create_run.execute(request=_request(harness), idempotency_key="key-blocked")


def test_rechaza_la_creacion_cuando_el_chunk_bundle_no_esta_registrado(harness) -> None:
    with pytest.raises(ChunkBundleNotFound):
        harness.create_run.execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id="chunk-bundle-desconocido",
                profile_id=harness.profile.profile_id,
            ),
            idempotency_key="key-missing",
        )


def test_el_claim_impide_ejecutar_dos_veces_el_mismo_run(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    first = harness.executor.execute(run.embedding_run_id)
    second = harness.executor.execute(run.embedding_run_id)

    assert first.status == "completed"
    assert second.embedding_run_id == first.embedding_run_id
    assert second.status == "completed"
    assert len(harness.bundles.list_bundles()) == 1


def test_el_bundle_es_determinista_cuando_se_repite_la_misma_fuente(harness) -> None:
    first_run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    first = harness.executor.execute(first_run.embedding_run_id)

    second_run = harness.create_run.execute(request=_request(harness), idempotency_key="key-2")
    second = harness.executor.execute(second_run.embedding_run_id)

    assert first.produced_embedding_bundle_id == second.produced_embedding_bundle_id


def test_la_reconciliacion_marca_como_fallido_un_run_interrumpido(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    harness.runs.claim(run.embedding_run_id)

    reconciled = harness.executor.reconcile()

    assert reconciled == [run.embedding_run_id]
    assert harness.runs.get(run.embedding_run_id).status == "failed"
    assert harness.runs.get(run.embedding_run_id).error_summary == "EMBEDDING_RUN_INTERRUPTED"


def test_el_run_falla_sin_dejar_bundle_cuando_el_perfil_pierde_la_verificacion(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    harness.profiles._profiles[harness.profile.profile_id] = harness.profile.model_copy(  # noqa: SLF001
        update={"compatibility_status": "compatibility_not_proven", "document_enabled": False}
    )

    failed = harness.executor.execute(run.embedding_run_id)

    assert failed.status == "failed"
    assert failed.error_summary == "EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN"
    assert harness.bundles.list_bundles() == []


def test_los_artefactos_publicados_conservan_rutas_relativas_y_checksums(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    completed = harness.executor.execute(run.embedding_run_id)
    bundle = harness.bundles.get(completed.produced_embedding_bundle_id)

    assert not Path(bundle.vector_artifact_relpath).is_absolute()
    assert not Path(bundle.chunk_map_relpath).is_absolute()
    assert set(bundle.checksums) >= {"vectors.npy", "chunk_map.jsonl"}
    assert harness.artifacts.verify_checksums(
        embedding_bundle_id=bundle.embedding_bundle_id,
        expected={
            key: value for key, value in bundle.checksums.items() if key != "manifest.json"
        },
    )


def test_el_chunk_map_cubre_cada_child_chunk_sin_duplicados(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    completed = harness.executor.execute(run.embedding_run_id)
    chunks = harness.bundles.list_chunks(completed.produced_embedding_bundle_id)

    assert [chunk.vector_offset for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.child_chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.vector_checksum for chunk in chunks)


def test_la_validacion_falla_cuando_el_contenido_fuente_cambio(harness, tmp_path) -> None:
    content = harness.content_reader.read(
        artifact_relpath=harness.chunk_bundle.artifact_relpath
    )
    engine = harness.registry.resolve_document_engine(harness.profile)
    built = harness.builder.build(
        profile=harness.profile,
        chunk_bundle=harness.chunk_bundle,
        content=content,
        engine=engine,
        engine_revision_observed="deterministic-v1",
    )

    drifted = content.__class__(
        parents=content.parents,
        children=content.children,
        source_content_fingerprint="9" * 64,
        corpus_version=content.corpus_version,
        document_id=content.document_id,
        source_relpath=content.source_relpath,
        source_hash=content.source_hash,
        normalized_relpath=content.normalized_relpath,
    )
    validation = harness.builder._validator.validate(  # noqa: SLF001
        bundle=built.bundle,
        profile=harness.profile,
        chunk_bundle=harness.chunk_bundle,
        content=drifted,
        chunks=built.chunks,
        vectors=harness.artifacts.load_vectors(
            vector_artifact_relpath=built.bundle.vector_artifact_relpath
        ),
    )

    assert validation.passed is False
    assert "source_content_fingerprint_matches" in {
        check.name for check in validation.failures()
    }


def test_no_sella_un_bundle_cuando_el_motor_devuelve_otra_dimension(harness) -> None:
    class WrongDimensionEngine:
        provider_name = "mock"
        model_name = "deterministic"
        dimension = 4
        normalization = "none"
        supports_queries = True

        def observe_revision(self) -> str:
            return "deterministic-v1"

        def embed_documents(self, texts):
            return [[0.1] * 4 for _ in texts]

        def embed_queries(self, texts):
            return self.embed_documents(texts)

    content = harness.content_reader.read(
        artifact_relpath=harness.chunk_bundle.artifact_relpath
    )

    with pytest.raises(EmbeddingBundleInvalid):
        harness.builder.build(
            profile=harness.profile,
            chunk_bundle=harness.chunk_bundle,
            content=content,
            engine=WrongDimensionEngine(),
            engine_revision_observed="deterministic-v1",
        )


def test_indexing_readiness_queda_lista_cuando_el_target_es_compatible(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    completed = harness.executor.execute(run.embedding_run_id)
    bundle = harness.bundles.get(completed.produced_embedding_bundle_id)

    readiness = EmbeddingIndexingReadinessEvaluator(targets=harness.targets).evaluate(
        bundle=bundle,
        profile=harness.profile,
    )

    assert readiness.status == "ready"
    assert readiness.blocking_reasons == []


def test_indexing_readiness_bloquea_cuando_el_target_usa_otra_metrica(harness) -> None:
    from embedding.infrastructure.in_memory.repositories import InMemoryIndexingTargetRepository

    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    completed = harness.executor.execute(run.embedding_run_id)
    bundle = harness.bundles.get(completed.produced_embedding_bundle_id)
    targets = InMemoryIndexingTargetRepository([build_target(distance_ops="vector_ip_ops")])

    readiness = EmbeddingIndexingReadinessEvaluator(targets=targets).evaluate(
        bundle=bundle,
        profile=harness.profile,
    )

    assert readiness.status == "blocked"
    assert "INDEXING_TARGET_INCOMPATIBLE" in readiness.blocking_reasons


def test_el_manifest_no_contiene_vectores_ni_texto(harness) -> None:
    run = harness.create_run.execute(request=_request(harness), idempotency_key="key-1")
    completed = harness.executor.execute(run.embedding_run_id)
    manifest = harness.artifacts.read_manifest(
        embedding_bundle_id=completed.produced_embedding_bundle_id
    )

    serialized = json.dumps(manifest)
    assert "safety rules" not in serialized
    assert "vectors" not in manifest
