from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from ingestion.schemas.common import StrictModel


ParseTier = Literal["fast", "cost_effective", "agentic", "agentic_plus"]
ClassifyMode = Literal["FAST"]
ExtractTier = Literal["cost_effective", "agentic", "agentic_plus"]
ParseExpand = Literal[
    "markdown",
    "markdown_full",
    "text",
    "text_full",
    "items",
    "metadata",
    "job_metadata",
]


class LlamaSettings(StrictModel):
    cloud_enabled: bool = False
    api_key: SecretStr | None = None
    parse_tier: ParseTier = "cost_effective"
    parse_version: str = "latest"
    parse_ocr_languages: tuple[str, ...] = ("es",)
    parse_expand: tuple[ParseExpand, ...] = ("markdown", "items", "metadata", "job_metadata")
    parse_max_concurrency: int = Field(default=2, ge=1)
    parse_timeout_seconds: int = Field(default=900, ge=1)
    parse_max_credits_per_run: int = Field(default=500, ge=0)
    parse_store_raw_results: bool = True
    parse_granular_bboxes: bool = False
    classify_mode: ClassifyMode = "FAST"
    classify_max_pages: int = Field(default=5, ge=1)
    extract_tier: ExtractTier = "cost_effective"
    extract_parse_tier: ParseTier = "fast"
    extract_max_pages: int = Field(default=5, ge=1)
    classify_enabled: bool = True
    extract_enabled: bool = True
    local_fallback_enabled: bool = True

    @field_validator("api_key", mode="before")
    @classmethod
    def normalize_blank_api_key(cls, value: Any) -> Any:
        if value == "":
            return None
        return value

    @field_validator("parse_ocr_languages", "parse_expand", mode="before")
    @classmethod
    def split_csv_values(cls, value: Any) -> Any:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def require_api_key_when_cloud_is_enabled(self) -> "LlamaSettings":
        if self.cloud_enabled and self.api_key is None:
            raise ValueError("LLAMA_CLOUD_API_KEY is required when LLAMA_CLOUD_ENABLED=true")
        return self

    def safe_model_dump(self) -> dict[str, Any]:
        data = self.model_dump()
        data["api_key"] = "***redacted***" if self.api_key is not None else None
        return data


def load_llama_settings(environ: dict[str, str] | None = None) -> LlamaSettings:
    env = os.environ if environ is None else environ
    return LlamaSettings(
        cloud_enabled=_env_bool(env, "LLAMA_CLOUD_ENABLED", False),
        api_key=env.get("LLAMA_CLOUD_API_KEY"),
        parse_tier=env.get("LLAMA_PARSE_TIER", "cost_effective"),
        parse_version=env.get("LLAMA_PARSE_VERSION", "latest"),
        parse_ocr_languages=env.get("LLAMA_PARSE_OCR_LANGUAGES", "es"),
        parse_expand=env.get("LLAMA_PARSE_EXPAND", "markdown,items,metadata,job_metadata"),
        parse_max_concurrency=_env_int(env, "LLAMA_PARSE_MAX_CONCURRENCY", 2),
        parse_timeout_seconds=_env_int(env, "LLAMA_PARSE_TIMEOUT_SECONDS", 900),
        parse_max_credits_per_run=_env_int(env, "LLAMA_PARSE_MAX_CREDITS_PER_RUN", 500),
        parse_store_raw_results=_env_bool(env, "LLAMA_PARSE_STORE_RAW_RESULTS", True),
        parse_granular_bboxes=_env_bool(env, "LLAMA_PARSE_GRANULAR_BBOXES", False),
        classify_mode=env.get("LLAMA_CLASSIFY_MODE", "FAST"),
        classify_max_pages=_env_int(env, "LLAMA_CLASSIFY_MAX_PAGES", 5),
        extract_tier=env.get("LLAMA_EXTRACT_TIER", "cost_effective"),
        extract_parse_tier=env.get("LLAMA_EXTRACT_PARSE_TIER", "fast"),
        extract_max_pages=_env_int(env, "LLAMA_EXTRACT_MAX_PAGES", 5),
        classify_enabled=_env_bool(env, "LLAMA_CLASSIFY_ENABLED", True),
        extract_enabled=_env_bool(env, "LLAMA_EXTRACT_ENABLED", True),
        local_fallback_enabled=_env_bool(env, "LLAMA_LOCAL_FALLBACK_ENABLED", True),
    )


def _env_bool(environ: dict[str, str], key: str, default: bool) -> bool:
    raw = environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(environ: dict[str, str], key: str, default: int) -> int:
    raw = environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)
