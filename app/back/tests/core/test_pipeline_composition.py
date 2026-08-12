"""Explicit persistence modes for the production composition root."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.dependencies import (
    PostgresUnavailableAtStartup,
    _resolve_persistence_mode,
    build_pipeline_services,
    build_pipeline_services_from_env,
)
from core.feature_flags import FeatureFlags


def test_resuelve_memory_por_defecto_sin_dsn() -> None:
    assert _resolve_persistence_mode({}) == "memory"


def test_feature_flags_quedan_activas_por_defecto_sin_env() -> None:
    flags = FeatureFlags.from_env({})

    assert flags.embedding_v2 is True
    assert flags.indexing_bundle_first is True
    assert flags.retrieval_v1 is True
    # Fase 6: la lane de plataforma está apagada por defecto.
    assert flags.rag_platform_v1 is False


def test_rag_platform_flag_se_lee_del_entorno() -> None:
    assert FeatureFlags.from_env(
        {"SST_FEATURE_RAG_PLATFORM_V1": "on"}
    ).rag_platform_v1 is True
    assert FeatureFlags.from_env({}).rag_platform_v1 is False


def test_flag_off_no_cablea_plataforma_y_deja_legacy_intacto(tmp_path: Path) -> None:
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        allow_mock_engine=True,
        feature_flags=FeatureFlags(rag_platform_v1=False),
    )
    try:
        assert services.rag_platform_publish is None
        # La superficie legacy de retrieval sigue construida.
        assert services.retrieval_search is not None
        assert services.indexing_activate is not None
    finally:
        services.close()


def test_flag_on_cablea_plataforma_sin_tocar_retrieval(tmp_path: Path) -> None:
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        allow_mock_engine=True,
        feature_flags=FeatureFlags(rag_platform_v1=True),
    )
    try:
        assert services.rag_platform_publish is not None
        # El wiring legacy de retrieval no cambia al habilitar la plataforma.
        assert services.retrieval_search is not None
        assert services.indexing_activate is not None
    finally:
        services.close()


def test_resuelve_postgres_cuando_hay_dsn() -> None:
    assert _resolve_persistence_mode({"SST_POSTGRES_DSN": "postgresql://x"}) == "postgres"


def test_modo_forzado_gana_sobre_el_dsn() -> None:
    env = {"SST_PERSISTENCE_MODE": "memory", "SST_POSTGRES_DSN": "postgresql://x"}
    assert _resolve_persistence_mode(env) == "memory"


def test_modo_invalido_falla_cerrado() -> None:
    with pytest.raises(ValueError):
        _resolve_persistence_mode({"SST_PERSISTENCE_MODE": "sqlite"})


def test_composicion_memory_no_abre_conexion(tmp_path: Path) -> None:
    services = build_pipeline_services_from_env(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        environ={},
        allow_mock_engine=True,
    )
    try:
        assert services.persistence_mode == "memory"
        assert services.connection is None
    finally:
        services.close()


def test_postgres_requerido_sin_dsn_falla_sin_degradar(tmp_path: Path) -> None:
    with pytest.raises(PostgresUnavailableAtStartup):
        build_pipeline_services_from_env(
            chunks_root=tmp_path / "chunks",
            embeddings_root=tmp_path / "embeddings",
            environ={"SST_PERSISTENCE_MODE": "postgres"},
        )


def test_postgres_con_dsn_inalcanzable_no_cae_a_memoria(tmp_path: Path) -> None:
    # A DSN pointing nowhere must fail closed, never silently serve from memory.
    env = {
        "SST_POSTGRES_DSN": "postgresql://user:pass@127.0.0.1:1/never",
        "SST_PERSISTENCE_MODE": "postgres",
    }
    with pytest.raises(PostgresUnavailableAtStartup) as excinfo:
        build_pipeline_services_from_env(
            chunks_root=tmp_path / "chunks",
            embeddings_root=tmp_path / "embeddings",
            environ=env,
        )
    # The sanitized message carries only the driver error class, no DSN.
    assert "user:pass" not in str(excinfo.value)


def test_composicion_emite_evento_de_startup_con_el_modo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []

    def _capture(**kwargs):
        captured.append(kwargs)

    # Capture at the emission boundary: the module logger's stream handler is
    # bound at import time, so patching the emitter is more robust than capsys.
    monkeypatch.setattr(
        "api.dependencies.emit_pipeline_event", lambda **kw: _capture(**kw)
    )

    services = build_pipeline_services_from_env(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        environ={},
        allow_mock_engine=True,
    )
    try:
        startup = [
            e for e in captured if e.get("event") == "pipeline_composition_ready"
        ]
        assert startup, "expected a pipeline_composition_ready event"
        assert startup[-1]["attributes"]["persistence_mode"] == "memory"
    finally:
        services.close()
