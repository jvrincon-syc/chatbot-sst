from __future__ import annotations

import pytest

from embedding.domain.models import (
    UNKNOWN_REVISION,
    EmbeddingBundle,
    EmbeddingConfigurationFingerprint,
    EmbeddingRun,
)

from pipeline_fixtures import build_profile


def test_fingerprint_es_estable_cuando_los_campos_semanticos_no_cambian() -> None:
    first = EmbeddingConfigurationFingerprint.compute(
        provider="bge",
        model="BAAI/bge-m3",
        model_revision="abc123",
        dimension=1024,
        normalization="l2",
        distance_metric="cosine",
        semantic_config={"pooling": "cls"},
    )
    second = EmbeddingConfigurationFingerprint.compute(
        provider="bge",
        model="BAAI/bge-m3",
        model_revision="abc123",
        dimension=1024,
        normalization="l2",
        distance_metric="cosine",
        semantic_config={"pooling": "cls"},
    )
    assert first == second


@pytest.mark.parametrize(
    "override",
    [
        {"provider": "voyage"},
        {"model": "voyage-4"},
        {"model_revision": "def456"},
        {"dimension": 512},
        {"normalization": "provider_normalized"},
        {"distance_metric": "l2"},
        {"semantic_config": {"pooling": "mean"}},
    ],
)
def test_fingerprint_cambia_cuando_cambia_un_campo_semantico(override: dict[str, object]) -> None:
    base = {
        "provider": "bge",
        "model": "BAAI/bge-m3",
        "model_revision": "abc123",
        "dimension": 1024,
        "normalization": "l2",
        "distance_metric": "cosine",
        "semantic_config": {"pooling": "cls"},
    }
    changed = {**base, **override}
    assert EmbeddingConfigurationFingerprint.compute(
        **base  # type: ignore[arg-type]
    ) != EmbeddingConfigurationFingerprint.compute(**changed)  # type: ignore[arg-type]


def test_perfil_legacy_queda_bloqueado_cuando_no_esta_verificado() -> None:
    profile = build_profile(
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
    )
    assert profile.is_verified is False
    assert profile.can_embed_documents is False
    assert profile.can_embed_queries is False


def test_perfil_bge_m3_legacy_queda_libre_para_embedding_operativo() -> None:
    profile = build_profile(
        provider="bge",
        model="BAAI/bge-m3",
        dimension=1024,
        normalization="unknown_normalization",
        vector_table="idx_vec_local_bge_m3_v1",
        compatibility_status="compatibility_not_proven",
        document_enabled=False,
        query_enabled=False,
    )

    assert profile.is_verified is False
    assert profile.can_embed_documents is True
    assert profile.can_embed_queries is True


def test_perfil_bloquea_documentos_cuando_esta_deprecado() -> None:
    from datetime import datetime, timezone

    profile = build_profile(deprecated_at=datetime(2026, 8, 5, tzinfo=timezone.utc))
    assert profile.can_embed_documents is False


def test_bundle_id_es_deterministico_para_la_misma_identidad() -> None:
    identity = {
        "source_chunk_bundle_id": "chunk-bundle-1",
        "embedding_profile_id": "p1",
        "configuration_fingerprint": "a" * 64,
        "corpus_version": "v1",
        "source_content_fingerprint": "b" * 64,
    }
    assert EmbeddingBundle.deterministic_id(**identity) == EmbeddingBundle.deterministic_id(
        **identity
    )
    assert EmbeddingBundle.deterministic_id(**identity) != EmbeddingBundle.deterministic_id(
        **{**identity, "corpus_version": "v2"}
    )


def test_bundle_lleva_project_id_de_plataforma_sin_alterar_identidad() -> None:
    """Fase 4 gap: el bundle transporta project_id, pero la identidad no cambia.

    project_id se puebla para bundles de plataforma (lo escribe el repositorio y
    lo usa el índice parcial de identidad física), es None para legacy, y NO forma
    parte de deterministic_id (id legacy preservado por ADR-007).
    """

    base = {
        "embedding_bundle_id": "eb-1",
        "source_chunk_bundle_id": "cb-1",
        "embedding_profile_id": "p1",
        "provider": "mock",
        "model": "m",
        "model_revision": "r",
        "dimension": 8,
        "normalization": "none",
        "distance_metric": "cosine",
        "configuration_fingerprint": "a" * 64,
        "corpus_version": "v1",
        "source_content_fingerprint": "b" * 64,
        "status": "pending",
    }
    legacy = EmbeddingBundle(**base)
    platform = EmbeddingBundle(**{**base, "project_id": "proj_alpha"})

    assert legacy.project_id is None
    assert platform.project_id == "proj_alpha"
    # deterministic_id no acepta project_id: la identidad legacy se conserva.
    import inspect

    assert "project_id" not in inspect.signature(EmbeddingBundle.deterministic_id).parameters


def test_run_es_terminal_cuando_alcanza_un_estado_final() -> None:
    run = EmbeddingRun(
        embedding_run_id="r1",
        idempotency_key="k1",
        request_fingerprint="c" * 64,
        source_chunk_bundle_id="chunk-bundle-1",
        embedding_profile_id="p1",
        runtime_engine="mock",
        runtime_mode="dry_run",
        engine_revision_observed=UNKNOWN_REVISION,
        status="running",
    )
    assert run.is_terminal is False
    assert run.model_copy(update={"status": "failed"}).is_terminal is True


def test_run_transporta_contexto_de_release_nullable() -> None:
    """Fase 4 gap #2: el run transporta project/variant/release, nullable.

    Legacy los deja en None; plataforma los recibe derivados del servidor. El
    adaptador Postgres los persiste (columnas de la migración 05); aquí se prueba
    el contrato de dominio (el round-trip real vive bajo postgres_live).
    """

    base = dict(
        embedding_run_id="r1",
        idempotency_key="k1",
        request_fingerprint="c" * 64,
        source_chunk_bundle_id="chunk-bundle-1",
        embedding_profile_id="p1",
        runtime_engine="mock",
        runtime_mode="dry_run",
        engine_revision_observed=UNKNOWN_REVISION,
        status="running",
    )
    legacy = EmbeddingRun(**base)
    assert (legacy.project_id, legacy.rag_variant_id, legacy.rag_release_id) == (
        None,
        None,
        None,
    )
    platform = EmbeddingRun(
        **base,
        project_id="proj_alpha",
        rag_variant_id="ragv_1",
        rag_release_id="ragr_1",
    )
    assert platform.project_id == "proj_alpha"
    assert platform.rag_variant_id == "ragv_1"
    assert platform.rag_release_id == "ragr_1"

    from embedding.infrastructure.postgres.repositories import _RUN_COLUMNS

    assert {"project_id", "rag_variant_id", "rag_release_id"} <= set(_RUN_COLUMNS)
