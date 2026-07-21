from __future__ import annotations

from ingestion.config.llama_settings import LlamaSettings
from ingestion.infrastructure.llama_cloud.parse_config import LlamaParseConfig


def test_parse_config_builds_v2_kwargs_from_settings() -> None:
    settings = LlamaSettings(
        parse_tier="cost_effective",
        parse_version="latest",
        parse_expand=("markdown", "items", "metadata", "job_metadata"),
        parse_ocr_languages=("es",),
        parse_timeout_seconds=900,
    )

    config = LlamaParseConfig.from_settings(settings)

    assert config.to_parse_kwargs() == {
        "tier": "cost_effective",
        "version": "latest",
        "expand": ["markdown", "items", "metadata", "job_metadata"],
        "processing_options": {"ocr_parameters": {"languages": ["es"]}},
        "processing_control": {"timeouts": {"base_in_seconds": 900}},
    }


def test_parse_config_hash_is_stable_and_excludes_secret_values() -> None:
    first = LlamaParseConfig(tier="cost_effective", version="latest")
    second = LlamaParseConfig(tier="cost_effective", version="latest")

    assert first.configuration_hash() == second.configuration_hash()
    assert "llx-" not in first.configuration_hash()


def test_fast_parse_config_drops_markdown_and_items_expands() -> None:
    config = LlamaParseConfig(
        tier="fast",
        expand=("markdown", "items", "text", "metadata", "job_metadata"),
    )

    assert config.to_parse_kwargs()["expand"] == ["text", "metadata", "job_metadata"]
