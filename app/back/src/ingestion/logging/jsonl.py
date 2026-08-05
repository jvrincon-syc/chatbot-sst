from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.logging.observability import (
    JsonScalar,
    ObservabilityEvent,
    sanitize_observability_payload,
    sanitize_observability_value,
)

class JsonlLogger:
    def __init__(self, path: Path, run_id: str, request_id: str | None = None) -> None:
        self.path = path
        self.run_id = run_id
        self.request_id = request_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(
        self,
        *,
        schema_version: str = "1.0",
        stage: str,
        event: str,
        status: str,
        message: str,
        level: str | None = None,
        request_id: str | None = None,
        document_id: Optional[str] = None,
        source_path: Optional[str] = None,
        provider: Optional[str] = None,
        capability: Optional[str] = None,
        job_id: Optional[str] = None,
        upstream_job_id: Optional[str] = None,
        configuration_hash: Optional[str] = None,
        result_count: Optional[int] = None,
        warning_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
        warning_code: Optional[str] = None,
        context: dict[str, JsonScalar] | None = None,
        metrics: dict[str, int | float] | None = None,
        attributes: dict[str, JsonScalar] | None = None,
        exception: Optional[BaseException] = None,
    ) -> None:
        payload = {
            "schema_version": schema_version,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "run_id": self.run_id,
            "request_id": request_id if request_id is not None else self.request_id,
            "document_id": document_id,
            "source_path": source_path,
            "stage": stage,
            "event": event,
            "status": status,
            "level": level or _level_for_status(status),
            "provider": provider,
            "capability": capability,
            "job_id": job_id,
            "upstream_job_id": upstream_job_id,
            "configuration_hash": configuration_hash,
            "result_count": result_count,
            "warning_count": warning_count,
            "duration_ms": duration_ms,
            "message": message,
            "warning_code": warning_code,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_trace": "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            if exception
            else None,
            "context": sanitize_observability_payload(context or {}),
            "metrics": sanitize_observability_payload(metrics or {}),
            "attributes": sanitize_observability_payload(attributes or {}),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def event_from_observability(
        self,
        event: ObservabilityEvent,
        *,
        stage: str | None = None,
        source_path: str | None = None,
        exception: Optional[BaseException] = None,
    ) -> None:
        """Persist a structured observability event in the durable JSONL log."""

        payload = event.to_jsonl_event(stage=stage, source_path=source_path)
        self.event(
            schema_version=str(payload["schema_version"]),
            stage=str(payload["stage"]),
            event=str(payload["event"]),
            status=str(payload["status"]),
            message=str(payload["message"]),
            request_id=payload.get("request_id"),
            document_id=payload.get("document_id"),
            source_path=payload.get("source_path"),
            provider=payload.get("provider"),
            capability=payload.get("capability"),
            job_id=payload.get("job_id"),
            upstream_job_id=payload.get("upstream_job_id"),
            configuration_hash=payload.get("configuration_hash"),
            result_count=payload.get("result_count"),
            warning_count=payload.get("warning_count"),
            duration_ms=payload.get("duration_ms"),
            warning_code=payload.get("warning_code"),
            context=payload.get("context"),
            metrics=payload.get("metrics"),
            attributes=payload.get("attributes"),
            exception=exception,
        )


def _level_for_status(status: str) -> str:
    if status in {"failed", "error"}:
        return "error"
    if status in {"skipped", "needs_review", "warning"}:
        return "warning"
    return "info"
