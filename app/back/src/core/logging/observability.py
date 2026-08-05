from __future__ import annotations

import logging
import re
from enum import Enum
from time import perf_counter
from typing import Protocol, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]

_REDACTED = "***redacted***"
_TRUNCATION_SUFFIX = "..."
_DEFAULT_MAX_STRING_LENGTH = 256
_DEFAULT_MAX_COLLECTION_PREVIEW = 8
_SENSITIVE_EXACT_KEYS = {
    "api_key",
    "authorization",
    "body",
    "chunk_text",
    "content",
    "credential",
    "document_text",
    "markdown",
    "password",
    "payload",
    "prompt",
    "raw",
    "raw_text",
    "request_body",
    "response",
    "secret",
    "signed_url",
    "text",
    "token",
    "url",
    "value_raw",
}
_SENSITIVE_SUFFIXES = ("_body", "_content", "_markdown", "_payload", "_text", "_url")
_SIGNED_URL_PATTERN = re.compile(
    r"https?://\S*(?:signature|x-amz-signature|x-goog-signature|token|auth|sig)=\S*",
    re.IGNORECASE,
)


class ObservabilityDomain(str, Enum):
    """High-level observability domains for structured backend events."""

    BACKEND = "backend"
    HTTP = "http"
    INGESTION = "ingestion"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    CLI = "cli"
    PROVIDER = "provider"
    EVALUATION = "evaluation"


class EventStatus(str, Enum):
    """Lifecycle status for structured events."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    REUSED = "reused"


class EventContext(BaseModel):
    """Execution context carried by structured observability events."""

    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    run_id: str | None = None
    document_id: str | None = None
    job_id: str | None = None
    upstream_job_id: str | None = None
    provider: str | None = None
    capability: str | None = None
    profile_id: str | None = None
    configuration_hash: str | None = None


class ObservabilityEvent(BaseModel):
    """Typed structured event that can be mirrored to stdout and JSONL."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    event: str = Field(min_length=1)
    domain: ObservabilityDomain
    status: EventStatus
    message: str = Field(min_length=1)
    context: EventContext = Field(default_factory=EventContext)
    metrics: dict[str, int | float] = Field(default_factory=dict)
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)

    @field_validator("metrics")
    @classmethod
    def _validate_metrics(cls, value: dict[str, int | float]) -> dict[str, int | float]:
        for metric_name, metric_value in value.items():
            if not metric_name:
                raise ValueError("metric names must not be empty")
            if isinstance(metric_value, bool):
                raise ValueError("metrics must be numeric")
        return value

    def to_log_payload(self) -> dict[str, JsonValue]:
        """Return a logger-friendly payload with redaction and truncation."""

        payload = self.model_dump(mode="json")
        payload["event_message"] = payload.pop("message")
        return sanitize_observability_value(payload, key=None)

    def to_jsonl_event(
        self,
        *,
        stage: str | None = None,
        source_path: str | None = None,
    ) -> dict[str, object]:
        """Return keyword arguments for ``JsonlLogger.event``."""

        payload = self.model_dump(mode="json", exclude_none=True)
        context = cast(dict[str, JsonScalar], payload.get("context", {}))
        metrics = cast(dict[str, int | float], payload.get("metrics", {}))
        attributes = cast(dict[str, JsonScalar], payload.get("attributes", {}))
        inferred_stage = stage or _json_scalar_to_str(attributes.get("stage")) or self.domain.value
        return {
            "schema_version": payload["schema_version"],
            "stage": inferred_stage,
            "event": payload["event"],
            "status": payload["status"],
            "message": payload["message"],
            "request_id": _json_scalar_to_str(context.get("request_id")),
            "document_id": _json_scalar_to_str(context.get("document_id")),
            "source_path": source_path,
            "provider": _json_scalar_to_str(context.get("provider")),
            "capability": _json_scalar_to_str(context.get("capability")),
            "job_id": _json_scalar_to_str(context.get("job_id")),
            "upstream_job_id": _json_scalar_to_str(context.get("upstream_job_id")),
            "configuration_hash": _json_scalar_to_str(context.get("configuration_hash")),
            "result_count": _metric_int_or_float(metrics.get("result_count")),
            "warning_count": _metric_int_or_float(metrics.get("warning_count")),
            "duration_ms": _metric_int_or_float(metrics.get("duration_ms")),
            "warning_code": _json_scalar_to_str(attributes.get("warning_code")),
            "context": context,
            "metrics": metrics,
            "attributes": attributes,
        }


class JsonlEventSink(Protocol):
    """Protocol for durable JSONL event sinks."""

    def event(self, **kwargs: object) -> None:
        """Persist one structured event."""


def emit_observability_event(
    *,
    logger: logging.Logger,
    event: ObservabilityEvent,
    jsonl_sink: JsonlEventSink | None = None,
    stage: str | None = None,
    source_path: str | None = None,
    exception: BaseException | None = None,
) -> None:
    """Emit a structured event to the configured runtime sinks."""

    level = _python_log_level(event.status)
    exc_info = (
        (type(exception), exception, exception.__traceback__)
        if exception is not None
        else None
    )
    logger.log(
        level,
        event.message,
        extra=event.to_log_payload(),
        exc_info=exc_info,
    )
    if jsonl_sink is not None:
        jsonl_sink.event(
            **event.to_jsonl_event(stage=stage, source_path=source_path),
            exception=exception,
        )


def measure_duration_ms(started_at: float) -> int:
    """Measure elapsed milliseconds using ``time.perf_counter``."""

    elapsed = perf_counter() - started_at
    return max(0, int(round(elapsed * 1000)))


def sanitize_observability_payload(payload: dict[str, object]) -> dict[str, JsonValue]:
    """Redact sensitive values and truncate long strings recursively."""

    return {
        key: sanitize_observability_value(value, key=key)
        for key, value in payload.items()
    }


def sanitize_observability_value(value: object, *, key: str | None = None) -> JsonValue:
    """Sanitize a value for structured logging."""

    if value is None or isinstance(value, (bool, int, float)):
        return cast(JsonValue, value)
    if isinstance(value, str):
        return _sanitize_string(value, key=key)
    if isinstance(value, Enum):
        return _sanitize_string(str(value.value), key=key)
    if isinstance(value, dict):
        if key is not None and _is_sensitive_key(key):
            return _REDACTED
        return {
            str(child_key): sanitize_observability_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        if key is not None and _is_sensitive_key(key):
            return _REDACTED
        items = list(value)
        preview = [
            sanitize_observability_value(child_value, key=key)
            for child_value in items[:_DEFAULT_MAX_COLLECTION_PREVIEW]
        ]
        if len(items) > _DEFAULT_MAX_COLLECTION_PREVIEW:
            preview.append(f"...(+{len(items) - _DEFAULT_MAX_COLLECTION_PREVIEW} more)")
        return preview
    return _sanitize_string(str(value), key=key)


def _sanitize_string(value: str, *, key: str | None = None) -> JsonValue:
    if not value:
        return value
    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if _SIGNED_URL_PATTERN.search(value):
        return _REDACTED
    if len(value) <= _DEFAULT_MAX_STRING_LENGTH:
        return value
    return value[: _DEFAULT_MAX_STRING_LENGTH - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def _is_sensitive_key(key: str) -> bool:
    folded = key.casefold()
    if folded in _SENSITIVE_EXACT_KEYS:
        return True
    return any(folded.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)


def _json_scalar_to_str(value: JsonScalar | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _metric_int_or_float(value: int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    return value


def _python_log_level(status: EventStatus) -> int:
    if status in {EventStatus.FAILED, EventStatus.REJECTED, EventStatus.BLOCKED}:
        return logging.ERROR
    if status in {EventStatus.WARNING, EventStatus.SKIPPED}:
        return logging.WARNING
    return logging.INFO
