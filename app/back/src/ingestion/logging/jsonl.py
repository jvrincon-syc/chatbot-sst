from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class JsonlLogger:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(
        self,
        *,
        stage: str,
        event: str,
        status: str,
        message: str,
        level: str | None = None,
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
        exception: Optional[BaseException] = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "run_id": self.run_id,
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
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _level_for_status(status: str) -> str:
    if status in {"failed", "error"}:
        return "error"
    if status in {"skipped", "needs_review", "warning"}:
        return "warning"
    return "info"
