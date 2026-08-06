import json
import logging

import pytest

from core.logging.logger import get_logger
from core.logging.observability import (
    EventContext,
    EventStatus,
    ObservabilityDomain,
    ObservabilityEvent,
    emit_observability_event,
)


def test_core_logging_package_is_included_cuando_backend_distribution_is_built() -> None:
    from setuptools import find_packages

    packages = set(find_packages("app/back/src"))

    assert "core" in packages
    assert "core.logging" in packages


def test_logger_emits_structured_info_to_stdout_cuando_context_is_provided(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("tests.core.logging.stdout")

    logger.info(
        "Processing document",
        extra={
            "run_id": "run_test",
            "document_id": "doc_123",
            "stage": "reading",
            "status": "started",
        },
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["level"] == "INFO"
    assert payload["message"] == "Processing document"
    assert payload["run_id"] == "run_test"
    assert payload["document_id"] == "doc_123"
    assert payload["stage"] == "reading"
    assert payload["status"] == "started"
    assert captured.err == ""
    assert logger.propagate is False
    assert any(handler.level <= logging.INFO for handler in logger.handlers)


def test_logger_redacts_sensitive_fields_and_truncates_largo_cuando_extra_contains_risk(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("tests.core.logging.redaction")

    logger.info(
        "Observability payload",
        extra={
            "api_key": "secret-value",
            "document_text": "contenido sensible",
            "summary": "x" * 300,
            "nested": {"token": "nested-secret", "safe": "ok"},
            "request_id": "req_123",
        },
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["api_key"] == "***redacted***"
    assert payload["document_text"] == "***redacted***"
    assert payload["nested"]["token"] == "***redacted***"
    assert payload["nested"]["safe"] == "ok"
    assert len(payload["summary"]) <= 256
    assert payload["request_id"] == "req_123"


def test_logger_does_not_duplicate_handlers_cuando_configuracion_se_repite() -> None:
    logger = get_logger("tests.core.logging.idempotent")
    logger = get_logger("tests.core.logging.idempotent")

    handler_names = [handler.name for handler in logger.handlers]

    assert handler_names.count("chatbot_sst_console") == 1
    assert handler_names.count("chatbot_sst_file") == 1


def test_observability_event_serializes_with_context_and_metrics_cuando_is_valid() -> None:
    event = ObservabilityEvent(
        event="pipeline_run_started",
        domain=ObservabilityDomain.INGESTION,
        status=EventStatus.STARTED,
        message="Pipeline started",
        context=EventContext(
            request_id="req_123",
            run_id="run_123",
            document_id="doc_123",
            provider="llama_cloud",
            capability="parse",
        ),
        metrics={"duration_ms": 42, "document_count": 7},
        attributes={"summary": "ok", "api_key": "secret-value"},
    )

    payload = event.to_log_payload()

    assert payload["schema_version"] == "1.0"
    assert payload["event"] == "pipeline_run_started"
    assert payload["domain"] == "ingestion"
    assert payload["status"] == "started"
    assert payload["context"]["request_id"] == "req_123"
    assert payload["metrics"]["duration_ms"] == 42
    assert payload["attributes"]["summary"] == "ok"
    assert payload["attributes"]["api_key"] == "***redacted***"


def test_emit_observability_event_uses_safe_log_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("tests.core.logging.observability.emit")
    event = ObservabilityEvent(
        event="backend_process_started",
        domain=ObservabilityDomain.BACKEND,
        status=EventStatus.STARTED,
        message="Backend process started",
        context=EventContext(run_id="run_123"),
    )

    emit_observability_event(logger=logger, event=event)

    payload = json.loads(capsys.readouterr().out)

    assert payload["message"] == "Backend process started"
    assert payload["event"] == "backend_process_started"
    assert payload["event_message"] == "Backend process started"
    assert payload["context"]["run_id"] == "run_123"


def test_logger_sanitiza_tracebacks_y_no_expone_rutas_ni_urls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("tests.core.logging.exceptions")

    try:
        try:
            raise ValueError(
                "provider failed at https://api.voyageai.com/v1/embeddings?token=abc123"
            )
        except ValueError as inner:
            raise RuntimeError(
                r"cache miss under C:\Users\svc\.cache\huggingface\models"
            ) from inner
    except RuntimeError:
        logger.error("embedding runtime failed", exc_info=True)

    captured = capsys.readouterr().out
    payload = json.loads(captured)

    # No raw traceback, no absolute paths, no URLs anywhere in the line.
    assert "exception" not in payload
    assert "Traceback" not in captured
    assert "huggingface" not in captured
    assert "voyageai.com" not in captured
    assert "C:\\Users" not in captured
    # Safe, correlatable summary instead.
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception_chain"] == "RuntimeError <- ValueError"
    assert len(payload["internal_error_id"]) == 16


def test_internal_error_id_es_estable_para_el_mismo_error() -> None:
    from core.logging.observability import internal_error_id

    error = RuntimeError("same failure")
    assert internal_error_id(error) == internal_error_id(error)


def test_observability_event_rejects_invalid_payload_cuando_event_is_empty() -> None:
    with pytest.raises(Exception):
        ObservabilityEvent(
            event="",
            domain=ObservabilityDomain.INGESTION,
            status=EventStatus.STARTED,
            message="Pipeline started",
        )
