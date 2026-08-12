"""Task 7: los wrappers CLI de plataforma fallan cerrado sin contexto válido.

Sin DSN de PostgreSQL el comando aborta con código 2 y no toca la BD. Verifica el
contrato operativo sin requerir infraestructura viva.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_DSN_ENV_VARS = (
    "SST_POSTGRES_DSN",
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PORT",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
)


def _load(module_name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clear_dsn(monkeypatch) -> None:
    for var in _DSN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_run_project_ingestion_falla_cerrado_sin_dsn(tmp_path, monkeypatch) -> None:
    _clear_dsn(monkeypatch)
    env_file = tmp_path / "secrets.env"
    env_file.write_text("", encoding="utf-8")
    module = _load("run_project_ingestion_cli", "scripts/rag_platform/run_project_ingestion.py")

    assert module.main(["--project-id", "proj_missing", "--env-file", str(env_file)]) == 2


def test_rebuild_platform_falla_cerrado_sin_dsn(tmp_path, monkeypatch) -> None:
    _clear_dsn(monkeypatch)
    env_file = tmp_path / "secrets.env"
    env_file.write_text("", encoding="utf-8")
    module = _load("rebuild_platform_cli", "scripts/rag_platform/rebuild_platform.py")

    assert module.main(["--project-id", "proj_missing", "--env-file", str(env_file)]) == 2
