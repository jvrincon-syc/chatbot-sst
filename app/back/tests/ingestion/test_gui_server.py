from __future__ import annotations

import pytest

from ingestion.gui.server import _llama_settings_for_pipeline_run


def test_gui_pipeline_settings_can_force_local_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "true")
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)

    settings = _llama_settings_for_pipeline_run({"providerMode": "local"})

    assert settings.cloud_enabled is False


def test_gui_pipeline_settings_accept_cloud_toggles_and_call_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "false")
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "test-key")

    settings = _llama_settings_for_pipeline_run(
        {
            "providerMode": "llama_cloud",
            "llamaCloud": {
                "classifyEnabled": True,
                "extractEnabled": False,
                "callOrder": "parse,classify,extract",
            },
        }
    )

    assert settings.cloud_enabled is True
    assert settings.classify_enabled is True
    assert settings.extract_enabled is False
    assert settings.call_order == ("parse", "classify", "extract")
