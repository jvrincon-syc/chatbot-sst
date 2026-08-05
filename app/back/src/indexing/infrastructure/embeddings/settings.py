from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator

from ingestion.schemas.common import StrictModel
from indexing.domain.profiles import DistanceMetric


EmbeddingRuntimeProvider = Literal["mock", "bge", "voyage", "cohere"]


class EmbeddingSettings(StrictModel):
    """Embedding runtime settings loaded at the infrastructure boundary."""

    provider: EmbeddingRuntimeProvider = "mock"
    model: str | None = None
    dimension: int | None = Field(default=None, gt=0)
    distance_metric: DistanceMetric = "cosine"
    batch_size: int = Field(default=32, ge=1)
    device: str = "cpu"
    hf_token: SecretStr | None = Field(default=None, repr=False)
    hf_hub_cache: str | None = None
    bge_use_fp16: bool = False
    bge_query_max_length: int = Field(default=512, ge=1)
    bge_document_max_length: int = Field(default=8192, ge=1)
    voyage_api_key: SecretStr | None = Field(default=None, repr=False)
    timeout_seconds: int = Field(default=30, ge=1)
    retries: int = Field(default=2, ge=0, le=5)

    @field_validator("hf_token", "voyage_api_key", mode="before")
    @classmethod
    def normalize_blank_secret(cls, value: Any) -> Any:
        """Treat blank secrets from template files as absent."""

        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "EmbeddingSettings":
        """Load embedding settings without requiring inactive provider secrets."""

        env = os.environ if environ is None else environ
        return cls(
            provider=env.get("EMBEDDING_PROVIDER", "mock"),
            model=env.get("EMBEDDING_MODEL") or None,
            dimension=_env_optional_int(env, "EMBEDDING_DIMENSION"),
            distance_metric=env.get("EMBEDDING_DISTANCE_METRIC", "cosine"),
            batch_size=_env_int(env, "EMBEDDING_BATCH_SIZE", 32),
            device=env.get("EMBEDDING_DEVICE", "cpu"),
            hf_token=env.get("HF_TOKEN"),
            hf_hub_cache=env.get("HF_HUB_CACHE") or None,
            bge_use_fp16=_env_bool(env, "BGE_USE_FP16", False),
            bge_query_max_length=_env_int(env, "BGE_QUERY_MAX_LENGTH", 512),
            bge_document_max_length=_env_int(env, "BGE_DOCUMENT_MAX_LENGTH", 8192),
            voyage_api_key=env.get("VOYAGE_API_KEY"),
            timeout_seconds=_env_int(env, "EMBEDDING_TIMEOUT_SECONDS", 30),
            retries=_env_int(env, "EMBEDDING_RETRIES", 2),
        )

    def safe_model_dump(self) -> dict[str, object]:
        """Return settings with secret values redacted."""

        data = self.model_dump()
        data["hf_token"] = "***redacted***" if self.hf_token is not None else None
        data["voyage_api_key"] = (
            "***redacted***" if self.voyage_api_key is not None else None
        )
        return data


def _env_bool(environ: Mapping[str, str], key: str, default: bool) -> bool:
    raw = environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw = environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_optional_int(environ: Mapping[str, str], key: str) -> int | None:
    raw = environ.get(key)
    if raw is None or raw == "":
        return None
    return int(raw)
