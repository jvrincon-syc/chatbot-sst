from __future__ import annotations

import json
from io import BytesIO

import pytest

from ingestion.gui.server import (
    ROOT,
    _document_ocr_confidence_for_record,
    _gui_settings_payload,
    _ingestion_details_for_record,
    _llama_settings_for_pipeline_run,
    _parse_multipart_form,
    _pipeline_run_options_from_body,
    _save_gui_settings,
    _staging_target_from_body,
    _validation_target_from_body,
)


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
    assert settings.local_fallback_enabled is False
    assert settings.classify_enabled is True
    assert settings.extract_enabled is False
    assert settings.call_order == ("parse", "classify", "extract")


def test_gui_pipeline_settings_accept_parser_only_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "false")
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "test-key")

    settings = _llama_settings_for_pipeline_run(
        {
            "providerMode": "llama_cloud",
            "llamaCloud": {
                "classifyEnabled": False,
                "extractEnabled": False,
                "callOrder": "parse",
            },
        }
    )

    assert settings.cloud_enabled is True
    assert settings.local_fallback_enabled is False
    assert settings.classify_enabled is False
    assert settings.extract_enabled is False
    assert settings.call_order == ("parse",)


def test_validation_target_uses_recent_staging_root() -> None:
    target = _validation_target_from_body({"stagingRoot": ".tmp/gui_phase1_test"})

    assert target.name == "staging"
    assert target.normalized_root == ROOT / ".tmp" / "gui_phase1_test"
    assert target.manifests_dir == ROOT / ".tmp" / "gui_phase1_test" / "_manifests"


def test_validation_target_rejects_paths_outside_tmp() -> None:
    with pytest.raises(ValueError, match="stagingRoot must stay under .tmp"):
        _validation_target_from_body({"stagingRoot": "data/docs_normalized"})


def test_promotion_target_requires_staging_root() -> None:
    with pytest.raises(ValueError, match="stagingRoot is required"):
        _staging_target_from_body({})


def test_promotion_target_uses_staging_root() -> None:
    target = _staging_target_from_body({"stagingRoot": ".tmp/gui_phase1_test"})

    assert target.name == "staging"
    assert target.normalized_root == ROOT / ".tmp" / "gui_phase1_test"


def test_ingestion_details_reads_provider_from_metadata(tmp_path) -> None:
    metadata_path = tmp_path / "convivencia_laboral" / "manual.metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps({"extraction_method": "llamaparse"}),
        encoding="utf-8",
    )

    details = _ingestion_details_for_record(
        {"source_relpath": "convivencia_laboral/manual.pdf"},
        normalized_root=tmp_path,
    )

    assert details == {
        "ingestionProvider": "llama_cloud",
        "ingestionProviderLabel": "LlamaCloud",
        "ingestionMethod": "llamaparse",
        "ingestionMethodLabel": "LlamaParse",
    }


def test_ingestion_details_marks_missing_metadata_as_unregistered(tmp_path) -> None:
    details = _ingestion_details_for_record(
        {"source_relpath": "general_sst/manual.pdf"},
        normalized_root=tmp_path,
    )

    assert details["ingestionProvider"] == "unregistered"
    assert details["ingestionProviderLabel"] == "Sin ingesta"
    assert details["ingestionMethodLabel"] == "Sin metadata normalizada"


def test_status_confidence_reads_inventory_value_as_percentage() -> None:
    confidence = _document_ocr_confidence_for_record(
        {
            "source_relpath": "general_sst/manual.pdf",
            "ocr_confidence": {"kind": "measured", "value": 0.873},
        }
    )

    assert confidence == {
        "ocrConfidenceKind": "measured",
        "ocrConfidenceValue": 0.873,
        "ocrConfidencePercent": 87.3,
        "ocrConfidenceLabel": "87.3%",
    }


def test_status_confidence_falls_back_to_metadata(tmp_path) -> None:
    metadata_path = tmp_path / "general_sst" / "manual.metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps({"ocr_confidence": {"kind": "measured", "value": 0.91}}),
        encoding="utf-8",
    )

    confidence = _document_ocr_confidence_for_record(
        {"source_relpath": "general_sst/manual.pdf"},
        normalized_root=tmp_path,
    )

    assert confidence["ocrConfidenceLabel"] == "91.0%"


def test_status_confidence_reports_na_when_unavailable() -> None:
    confidence = _document_ocr_confidence_for_record(
        {
            "source_relpath": "general_sst/manual.pdf",
            "ocr_confidence": {"kind": "unavailable", "value": None},
        }
    )

    assert confidence["ocrConfidenceKind"] == "unavailable"
    assert confidence["ocrConfidencePercent"] is None
    assert confidence["ocrConfidenceLabel"] == "N/A"


def test_gui_settings_persist_ocr_review_threshold(tmp_path) -> None:
    settings_path = tmp_path / "gui_settings.json"

    saved = _save_gui_settings(
        {"ocrReviewThresholdPercent": 83},
        settings_path=settings_path,
    )
    loaded = _gui_settings_payload(settings_path=settings_path)

    assert saved["ocrReviewThreshold"] == 0.83
    assert loaded["ocrReviewThresholdPercent"] == 83.0


def test_pipeline_run_options_use_saved_ocr_threshold(tmp_path) -> None:
    settings_path = tmp_path / "gui_settings.json"
    _save_gui_settings(
        {"ocrReviewThresholdPercent": 77},
        settings_path=settings_path,
    )

    options = _pipeline_run_options_from_body({}, settings_path=settings_path)

    assert options["ocr_review_threshold"] == 0.77


def test_parse_multipart_form_reads_fields_and_uploaded_file() -> None:
    boundary = "----phase1"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="category"\r\n'
        "\r\n"
        "politicas\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="folder"\r\n'
        "\r\n"
        "sst\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="manual.pdf"\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
        "%PDF-1.4\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    form = _parse_multipart_form(
        content_type=f"multipart/form-data; boundary={boundary}",
        content_length=str(len(body)),
        body=BytesIO(body),
    )

    assert form["category"] == "politicas"
    assert form["folder"] == "sst"
    assert form["file"].filename == "manual.pdf"
    assert form["file"].file.read() == b"%PDF-1.4"
