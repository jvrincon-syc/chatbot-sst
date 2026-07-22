from __future__ import annotations

from typing import cast

from ingestion.domain.models.provider import ProviderJobStatus


def coerce_provider_job_status(value: object) -> ProviderJobStatus:
    status = str(value or "completed").lower()
    if status in {"pending", "running", "completed", "failed", "cancelled"}:
        return cast(ProviderJobStatus, status)
    return "completed"
