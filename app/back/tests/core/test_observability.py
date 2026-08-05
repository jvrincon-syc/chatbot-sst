from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.logging.observability import (
    EventContext,
    EventStatus,
    ObservabilityDomain,
    ObservabilityEvent,
    measure_duration_ms,
    sanitize_observability_payload,
)
from ingestion.logging.jsonl import JsonlLogger


def test_measure_duration_ms_returns_non_negative_cuando_el_reloj_avanza() -> None:
    assert measure_duration_ms(0.0) >= 0


def test_sanitize_observability_payload_redacts_signed_urls_y_document_content() -> None:
    payload = sanitize_observability_payload(
        {
            "signed_url": "https://example.com/file?X-Amz-Signature=abc",
            "prompt": "contenido del prompt",
            "safe": "ok",
        }
    )

    assert payload["signed_url"] == "***redacted***"
    assert payload["prompt"] == "***redacted***"
    assert payload["safe"] == "ok"


def test_jsonl_logger_persists_observability_envelope_cuando_event_is_structured(
    tmp_path: Path,
) -> None:
    logger = JsonlLogger(tmp_path / "run_details.log", "run_123", request_id="req_123")
    event = ObservabilityEvent(
        event="backend_process_started",
        domain=ObservabilityDomain.BACKEND,
        status=EventStatus.STARTED,
        message="Backend process started",
        context=EventContext(
            request_id="req_123",
            run_id="run_123",
            provider="llama_cloud",
        ),
        metrics={"duration_ms": 17},
        attributes={"host": "127.0.0.1", "api_key": "secret"},
    )

    logger.event_from_observability(event, stage="backend", source_path="gui/server")

    payload = json.loads((tmp_path / "run_details.log").read_text(encoding="utf-8").strip())

    assert payload["schema_version"] == "1.0"
    assert payload["run_id"] == "run_123"
    assert payload["request_id"] == "req_123"
    assert payload["stage"] == "backend"
    assert payload["event"] == "backend_process_started"
    assert payload["context"]["request_id"] == "req_123"
    assert payload["metrics"]["duration_ms"] == 17
    assert payload["attributes"]["api_key"] == "***redacted***"
    assert payload["source_path"] == "gui/server"
