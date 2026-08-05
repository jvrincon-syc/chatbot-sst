from __future__ import annotations

import os
from pathlib import Path

from ingestion.config.llama_settings import LlamaSettings, load_llama_settings


def load_secrets_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_runtime_llama_settings(secrets_path: Path | None = None) -> LlamaSettings:
    if secrets_path is not None:
        load_secrets_env(secrets_path)
    return load_llama_settings()
