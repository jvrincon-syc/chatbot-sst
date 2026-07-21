from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_serializer, model_validator

from ingestion.schemas.common import StrictModel


ProviderCapability = Literal["parse", "classify", "extract"]
ProviderJobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class ProviderJobRef(StrictModel):
    provider: str = Field(min_length=1)
    capability: ProviderCapability
    job_id: str = Field(min_length=1)
    status: ProviderJobStatus
    configuration_hash: str = Field(min_length=1)
    created_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_completion_order(self) -> "ProviderJobRef":
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at must be greater than or equal to created_at")
        return self

    @field_serializer("created_at", "completed_at", when_used="json")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat().replace("+00:00", "Z")
