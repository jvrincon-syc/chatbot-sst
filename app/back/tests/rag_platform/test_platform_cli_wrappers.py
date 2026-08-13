"""Task 7: los wrappers CLI de plataforma fallan cerrado sin contexto válido.

Sin DSN de PostgreSQL el comando aborta con código 2 y no toca la BD. Verifica el
contrato operativo sin requerir infraestructura viva.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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
    # Registrar antes de exec: dataclasses/typing resuelven anotaciones-string vía
    # sys.modules[cls.__module__]; sin esto el @dataclass del módulo falla al cargar.
    sys.modules[module_name] = module
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


def test_rebuild_platform_falla_cerrado_sin_perfil_de_embedding(
    tmp_path, monkeypatch, capsys
) -> None:
    """Con proyecto válido pero sin variante ni perfil explícito, aborta fail-closed."""

    env_file = tmp_path / "secrets.env"
    env_file.write_text("", encoding="utf-8")
    module = _load("rebuild_platform_cli", "scripts/rag_platform/rebuild_platform.py")

    # Evita tocar Postgres: fuerza un DSN y un contexto sin perfil de embedding.
    monkeypatch.setattr(module, "load_env_file", lambda path: {})
    monkeypatch.setattr(module, "build_dsn_from_env", lambda env: "postgresql://x/y")
    monkeypatch.setattr(
        module,
        "_resolve_context",
        lambda **_: module._ResolvedContext(
            project=object(),
            rag_variant_id=None,
            semantic_recipe_fingerprint=None,
            embedding_profile_id=None,
        ),
    )

    assert module.main(["--project-id", "proj_x", "--env-file", str(env_file)]) == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["reason"] == "embedding_profile_unresolved"
