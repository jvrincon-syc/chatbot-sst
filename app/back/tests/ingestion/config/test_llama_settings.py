from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from ingestion.config.llama_settings import LlamaSettings, load_llama_settings


def test_llama_settings_loads_plan_defaults_when_env_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.startswith("LLAMA_"):
            monkeypatch.delenv(key, raising=False)

    settings = load_llama_settings()

    assert settings.cloud_enabled is False
    assert settings.parse_tier == "cost_effective"
    assert settings.parse_version == "latest"
    assert settings.parse_ocr_languages == ("es",)
    assert settings.parse_expand == ("markdown", "items", "metadata", "job_metadata")
    assert settings.parse_max_concurrency == 2
    assert settings.parse_timeout_seconds == 900
    assert settings.parse_max_credits_per_run == 500
    assert settings.parse_store_raw_results is True
    assert settings.parse_granular_bboxes is False
    assert settings.classify_mode == "FAST"
    assert settings.classify_max_pages == 5
    assert settings.extract_tier == "cost_effective"
    assert settings.extract_parse_tier == "fast"
    assert settings.extract_max_pages == 5
    assert settings.classify_enabled is True
    assert settings.extract_enabled is True
    assert settings.call_order == ("classify", "parse", "extract")
    assert settings.local_fallback_enabled is True


def test_llama_settings_requires_api_key_when_cloud_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "true")
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "")

    with pytest.raises(ValidationError, match="LLAMA_CLOUD_API_KEY"):
        load_llama_settings()


def test_llama_settings_accepts_cloud_enabled_with_key_and_csv_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "true")
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "llx-test")
    monkeypatch.setenv("LLAMA_PARSE_OCR_LANGUAGES", "es,en")
    monkeypatch.setenv("LLAMA_PARSE_EXPAND", "markdown,items")
    monkeypatch.setenv("LLAMA_PARSE_MAX_CONCURRENCY", "4")

    settings = load_llama_settings()

    assert settings.cloud_enabled is True
    assert settings.api_key.get_secret_value() == "llx-test"
    assert settings.parse_ocr_languages == ("es", "en")
    assert settings.parse_expand == ("markdown", "items")
    assert settings.parse_max_concurrency == 4


def test_llama_settings_accepts_configurable_call_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CALL_ORDER", "parse,classify,extract")

    settings = load_llama_settings()

    assert settings.call_order == ("parse", "classify", "extract")


def test_llama_settings_rejects_extract_before_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CALL_ORDER", "classify,extract,parse")

    with pytest.raises(ValidationError, match="LlamaExtract must run after LlamaParse"):
        load_llama_settings()


def test_llama_settings_rejects_classify_after_extract_when_both_are_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLAMA_CALL_ORDER", "parse,extract,classify")

    with pytest.raises(ValidationError, match="LlamaClassify must run before LlamaExtract"):
        load_llama_settings()


def test_llama_settings_accepts_parse_only_when_optional_stops_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLAMA_CLASSIFY_ENABLED", "false")
    monkeypatch.setenv("LLAMA_EXTRACT_ENABLED", "false")
    monkeypatch.setenv("LLAMA_CALL_ORDER", "parse")

    settings = load_llama_settings()

    assert settings.call_order == ("parse",)


def test_llama_settings_redacts_secret_from_dump() -> None:
    settings = LlamaSettings(cloud_enabled=True, api_key="llx-secret")

    dumped = settings.safe_model_dump()

    assert dumped["api_key"] == "***redacted***"
    assert "llx-secret" not in repr(settings)
