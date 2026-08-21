from __future__ import annotations

import json
from http import HTTPStatus
from io import BytesIO

import pytest

import ingestion.gui.server as gui_server
from ingestion.config.llama_settings import LlamaSettings
from ingestion.gui.server import (
    Phase1GuiHandler,
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
    assert _request_route_for_log("/api/chunking/documents") == "/api/chunking/documents"
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


def test_gui_common_headers_allow_pipeline_idempotency_and_auth_headers() -> None:
    sent_headers: list[tuple[str, str]] = []

    class _FakeHandler:
        def send_header(self, name: str, value: str) -> None:
            sent_headers.append((name, value))

    Phase1GuiHandler._send_common_headers(_FakeHandler())  # type: ignore[arg-type]

    headers = dict(sent_headers)
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert headers["Access-Control-Allow-Methods"] == "GET, POST, PATCH, OPTIONS"
    allowed_headers = headers["Access-Control-Allow-Headers"]
    assert "Content-Type" in allowed_headers
    assert "Idempotency-Key" in allowed_headers
    assert "Authorization" in allowed_headers


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


def test_gui_backend_builds_chunking_bridge_without_sharing_pipeline_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_chunking_kwargs: dict[str, object] = {}

    class _FakeChunkingApi:
        def close(self) -> None:
            return None

    class _FakeReconciler:
        def reconcile(self) -> None:
            return None

    class _FakeExecutor:
        def reconcile(self) -> None:
            return None

    class _FakePipelineServices:
        def __init__(self) -> None:
            self.connection = object()
            self.indexing_reconciler = _FakeReconciler()
            self.embedding_executor = _FakeExecutor()
            # main() cablea la sesión GUI con la MISMA autoridad de auth que FastAPI;
            # el doble debe exponerla igual que el PipelineServices real.
            self.http_authenticator = object()

        def close(self) -> None:
            return None

    class _FakeServer:
        def __init__(self, *_args, **_kwargs) -> None:
            self.chunking_api = None
            self.pipeline_api = None

        def serve_forever(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    def _fake_chunking_api_bridge(**kwargs):
        captured_chunking_kwargs.update(kwargs)
        return _FakeChunkingApi()

    monkeypatch.setattr(gui_server, "configure_structured_logging", lambda **_kwargs: None)
    monkeypatch.setattr(gui_server, "load_secrets_env", lambda _path: None)
    monkeypatch.setattr(
        gui_server,
        "build_pipeline_services_from_env",
        lambda **_kwargs: _FakePipelineServices(),
    )
    monkeypatch.setattr(gui_server, "ChunkingApiBridge", _fake_chunking_api_bridge)
    monkeypatch.setattr(gui_server, "create_app", lambda **_kwargs: object())
    monkeypatch.setattr(gui_server, "AsgiBridge", lambda _app: object())
    monkeypatch.setattr(gui_server, "ThreadingHTTPServer", _FakeServer)
    # La sesión GUI (auth por cookie + directorio local de operadores) se aísla
    # como el resto de dependencias pesadas: este test solo verifica el wiring del
    # chunking bridge, no el registro de operadores en disco.
    monkeypatch.setattr(gui_server, "LocalOperatorDirectory", lambda _path: object())
    monkeypatch.setattr(gui_server, "GuiAuthCoordinator", lambda **_kwargs: object())

    assert gui_server.main() == 0
    assert captured_chunking_kwargs["docs_normalized"] == gui_server.DOCS_NORMALIZED
    assert captured_chunking_kwargs["chunks_root"] == gui_server.CHUNKING_ROOT
    assert "connection" not in captured_chunking_kwargs


# --------------------------------------------------------------------------- #
# Gate 0 (Fase 8): bridge GUI -> FastAPI para /api/platform incluido PATCH     #
# --------------------------------------------------------------------------- #


class _BridgeResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {"content-type": "application/json"}


class _RecordingBridge:
    """Doble del ``AsgiBridge``: registra la llamada y devuelve una respuesta fija."""

    def __init__(self, response: _BridgeResponse) -> None:
        self._response = response
        self.calls: list[dict] = []

    def handle(self, *, method, path, headers, body):
        self.calls.append(
            {"method": method, "path": path, "headers": headers, "body": body}
        )
        return self._response


def _make_handler(*, path, headers, body, bridge):
    handler = Phase1GuiHandler.__new__(Phase1GuiHandler)
    handler.path = path
    handler.headers = dict(headers)
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.client_address = None
    handler._response_status_code = None
    handler.sent_headers = {}
    handler.send_response = lambda status, *a: None
    handler.send_header = lambda name, value: handler.sent_headers.__setitem__(name, value)
    handler.end_headers = lambda: None

    class _Server:
        pass

    server = _Server()
    server.pipeline_api = bridge
    handler.server = server
    return handler


def test_platform_prefix_is_in_the_bridge_allowlist() -> None:
    assert "/api/platform/projects".startswith(gui_server.PIPELINE_API_PREFIXES)


def test_platform_get_is_forwarded_to_fastapi_bridge() -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b'{"items":[]}'))
    handler = _make_handler(
        path="/api/platform/projects", headers={}, body=b"", bridge=bridge
    )
    handler._handle_pipeline_api("GET")
    assert bridge.calls[0]["method"] == "GET"
    assert bridge.calls[0]["path"] == "/api/platform/projects"
    assert handler.wfile.getvalue() == b'{"items":[]}'
    assert handler._response_status_code == HTTPStatus(200)


def test_platform_post_is_forwarded_to_fastapi_bridge() -> None:
    bridge = _RecordingBridge(_BridgeResponse(201, b'{"project_id":"proj_demo"}'))
    body = b'{"project_slug":"demo","display_name":"Demo"}'
    handler = _make_handler(
        path="/api/platform/projects",
        headers={"Content-Length": str(len(body))},
        body=body,
        bridge=bridge,
    )
    handler._handle_pipeline_api("POST")
    assert bridge.calls[0]["method"] == "POST"
    assert bridge.calls[0]["body"] == body
    assert handler._response_status_code == HTTPStatus(201)


def test_platform_patch_is_forwarded_with_headers_and_body() -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b'{"display_name":"x"}'))
    body = b'{"display_name":"x"}'
    handler = _make_handler(
        path="/api/platform/projects/proj_demo",
        headers={"Content-Length": str(len(body)), "Authorization": "Bearer tk"},
        body=body,
        bridge=bridge,
    )
    handler.do_PATCH()
    call = bridge.calls[0]
    assert call["method"] == "PATCH"
    assert call["path"] == "/api/platform/projects/proj_demo"
    assert call["body"] == body
    assert handler._response_status_code == HTTPStatus(200)


def test_platform_bridge_preserves_auth_and_idempotency_headers() -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b"{}"))
    handler = _make_handler(
        path="/api/platform/releases/ragr_x/build",
        headers={"Authorization": "Bearer tk", "Idempotency-Key": "key-1"},
        body=b"",
        bridge=bridge,
    )
    handler._handle_pipeline_api("POST")
    forwarded = bridge.calls[0]["headers"]
    assert forwarded["Authorization"] == "Bearer tk"
    assert forwarded["Idempotency-Key"] == "key-1"


def test_platform_bridge_exception_returns_500_envelope_instead_of_resetting_socket() -> None:
    class _ExplodingBridge:
        def handle(self, **_kwargs):
            raise RuntimeError("boom")

    handler = _make_handler(
        path="/api/platform/projects/proj_demo/variant-matrix",
        headers={},
        body=b"",
        bridge=_ExplodingBridge(),
    )

    handler._handle_pipeline_api("GET")

    assert handler._response_status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {
        "error": {
            "code": "PIPELINE_BRIDGE_ERROR",
            "message": "pipeline bridge failed: RuntimeError",
            "run_id": None,
            "details": {},
        }
    }


@pytest.mark.parametrize("status_code", [401, 403, 409, 422, 503])
def test_platform_bridge_preserves_error_status_and_envelope(status_code: int) -> None:
    envelope = b'{"error":{"code":"X","message":"m","run_id":null,"details":{}}}'
    bridge = _RecordingBridge(_BridgeResponse(status_code, envelope))
    handler = _make_handler(
        path="/api/platform/projects", headers={}, body=b"", bridge=bridge
    )
    handler._handle_pipeline_api("GET")
    assert handler._response_status_code == HTTPStatus(status_code)
    assert handler.wfile.getvalue() == envelope
