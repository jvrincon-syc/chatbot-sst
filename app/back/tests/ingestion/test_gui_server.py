from __future__ import annotations

import json
from io import BytesIO

import pytest

import ingestion.gui.server as gui_server
from ingestion.config.llama_settings import LlamaSettings
from ingestion.gui.server import (
    ROOT,
    ReviewDecision,
    _document_payload_for_record,
    _document_ocr_confidence_for_record,
    _gui_settings_payload,
    _ingestion_details_for_record,
    _llama_settings_for_pipeline_run,
    _parse_multipart_form,
    _redact_client_address,
    _request_route_for_log,
    _pipeline_run_options_from_body,
    _save_gui_settings,
    _staging_target_from_body,
    _validation_target_from_body,
    build_status_payload,
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


def test_gui_pipeline_settings_reject_cloud_when_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def settings_without_api_key(_path: object) -> LlamaSettings:
        return LlamaSettings(cloud_enabled=False)

    monkeypatch.setattr(
        gui_server,
        "load_runtime_llama_settings",
        settings_without_api_key,
    )

    with pytest.raises(ValueError, match="LLAMA_CLOUD_API_KEY is required"):
        _llama_settings_for_pipeline_run({"providerMode": "llama_cloud"})


def test_gui_http_logging_redacts_sensitive_route_segments() -> None:
    assert _request_route_for_log("/api/review/doc_123") == "/api/review/{document_id}"
    assert (
        _request_route_for_log("/api/chunking/runs/run_123")
        == "/api/chunking/runs/{run_id}"
    )
    assert (
        _request_route_for_log("/api/chunking/runs/run_123/documents")
        == "/api/chunking/runs/{run_id}/documents"
    )
    assert (
        _request_route_for_log("/api/chunking/runs/run_123/validation")
        == "/api/chunking/runs/{run_id}/validation"
    )
    assert (
        _request_route_for_log("/api/chunking/documents/doc_123/parents")
        == "/api/chunking/documents/{document_id}/parents"
    )
    assert (
        _request_route_for_log("/api/chunking/parents/parent_123/children")
        == "/api/chunking/parents/{parent_id}/children"
    )


def test_gui_http_logging_redacts_client_address() -> None:
    assert _redact_client_address(("127.0.0.1", 1234)) == "***redacted***"
    assert _redact_client_address(None) is None


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
        "ingestionProviderLabel": "Llama",
        "ingestionMethod": "llamaparse",
        "ingestionMethodLabel": "LlamaParse",
    }


def test_ingestion_details_reads_llama_provider_from_metadata_even_without_method(tmp_path) -> None:
    metadata_path = tmp_path / "convivencia_laboral" / "manual.metadata.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps({"llama_cloud": {"parse_job_id": "pjb_123"}}),
        encoding="utf-8",
    )

    details = _ingestion_details_for_record(
        {"source_relpath": "convivencia_laboral/manual.pdf"},
        normalized_root=tmp_path,
    )

    assert details["ingestionProvider"] == "llama_cloud"
    assert details["ingestionProviderLabel"] == "Llama"
    assert details["ingestionMethodLabel"] == "LlamaParse"


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


def test_document_payload_marks_processed_review_decision_as_not_required(tmp_path) -> None:
    document = _document_payload_for_record(
        {
            "document_id": "doc_123",
            "source_relpath": "general_sst/manual.md",
            "document_name": "manual.md",
            "processing_status": "processed",
        },
        review_item={},
        decision=None,
        normalized_root=tmp_path,
    )

    assert document["processingStatus"] == "processed"
    assert document["displayStatus"] == "processed"
    assert document["reviewStatus"] == "not_required"
    assert document["decision"] is None


def test_document_payload_marks_reviewed_needs_review_as_decided(tmp_path) -> None:
    decision = ReviewDecision(
        document_id="doc_123",
        source_relpath="general_sst/manual.pdf",
        decision="approved",
        reason="Revision humana completada.",
        decided_at="2026-07-22T10:00:00-05:00",
    )

    document = _document_payload_for_record(
        {
            "document_id": "doc_123",
            "source_relpath": "general_sst/manual.pdf",
            "document_name": "manual.pdf",
            "processing_status": "needs_review",
        },
        review_item={"reasons": ["low_ocr_confidence"]},
        decision=decision,
        normalized_root=tmp_path,
    )

    assert document["processingStatus"] == "needs_review"
    assert document["displayStatus"] == "approved"
    assert document["reviewStatus"] == "approved"


def test_status_payload_counts_decisions_for_current_inventory(tmp_path) -> None:
    normalized_root = tmp_path / "normalized"
    manifests_dir = normalized_root / "_manifests"
    manifests_dir.mkdir(parents=True)
    (manifests_dir / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": "doc_pending",
                        "source_relpath": "general_sst/pending.pdf",
                        "processing_status": "needs_review",
                    },
                    {
                        "document_id": "doc_approved",
                        "source_relpath": "general_sst/approved.pdf",
                        "processing_status": "needs_review",
                    },
                    {
                        "document_id": "doc_processed",
                        "source_relpath": "general_sst/processed.pdf",
                        "processing_status": "processed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (manifests_dir / "needs_review.json").write_text(
        json.dumps(
            {
                "items": [
                    {"document_id": "doc_pending", "reasons": ["low_confidence"]},
                    {"document_id": "doc_approved", "reasons": ["low_confidence"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (manifests_dir / "errors.json").write_text(
        json.dumps({"items": []}),
        encoding="utf-8",
    )
    (manifests_dir / "gui_settings.json").write_text(
        json.dumps(
            {
                "ocr_review_threshold": 0.88,
                "llama_controls": {
                    "providerMode": "llama_cloud",
                    "route": "classify,parse,extract",
                },
                "updated_at": "2026-07-22T10:00:00-05:00",
            }
        ),
        encoding="utf-8",
    )
    review_decisions_path = manifests_dir / "review_decisions.json"
    review_decisions_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "document_id": "doc_approved",
                        "source_relpath": "general_sst/approved.pdf",
                        "decision": "approved",
                        "reason": "Revision humana completada.",
                        "decided_at": "2026-07-22T10:00:00-05:00",
                    },
                    {
                        "document_id": "doc_outside_inventory",
                        "source_relpath": "general_sst/outside.pdf",
                        "decision": "rejected",
                        "reason": "No pertenece al corpus vigente.",
                        "decided_at": "2026-07-22T10:00:00-05:00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_status_payload(
        normalized_root=normalized_root,
        manifests_dir=manifests_dir,
        review_decisions_path=review_decisions_path,
        settings_path=manifests_dir / "gui_settings.json",
    )

    assert payload["summary"]["needsReview"] == 1
    assert payload["summary"]["normalizedNeedsReview"] == 2
    assert payload["summary"]["approved"] == 1
    assert payload["summary"]["rejected"] == 0
    assert payload["settings"]["ocrReviewThresholdPercent"] == 88.0
    assert payload["settings"]["llamaControls"] == {
        "providerMode": "llama_cloud",
        "route": "classify,parse,extract",
    }


def test_gui_settings_persist_ocr_review_threshold(tmp_path) -> None:
    settings_path = tmp_path / "gui_settings.json"

    saved = _save_gui_settings(
        {
            "ocrReviewThresholdPercent": 83,
            "providerMode": "llama_cloud",
            "route": "parse,classify",
        },
        settings_path=settings_path,
    )
    loaded = _gui_settings_payload(settings_path=settings_path)

    assert saved["ocrReviewThreshold"] == 0.83
    assert saved["llamaControls"] == {
        "providerMode": "llama_cloud",
        "route": "parse,classify",
    }
    assert loaded["ocrReviewThresholdPercent"] == 83.0
    assert loaded["llamaControls"] == {
        "providerMode": "llama_cloud",
        "route": "parse,classify",
    }


def test_pipeline_run_options_use_saved_ocr_threshold(tmp_path) -> None:
    settings_path = tmp_path / "gui_settings.json"
    _save_gui_settings(
        {
            "ocrReviewThresholdPercent": 77,
            "providerMode": "local",
            "route": "classify,parse,extract",
        },
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
