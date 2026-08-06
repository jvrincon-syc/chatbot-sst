"""Explicit persistence modes for the production composition root."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.dependencies import (
    PostgresUnavailableAtStartup,
    _resolve_persistence_mode,
    build_pipeline_services_from_env,
)


def test_resuelve_memory_por_defecto_sin_dsn() -> None:
    assert _resolve_persistence_mode({}) == "memory"


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
