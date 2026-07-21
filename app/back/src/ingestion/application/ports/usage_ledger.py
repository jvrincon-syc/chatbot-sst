from __future__ import annotations

from typing import Protocol

from pydantic import Field

from ingestion.domain.models.provider import ProviderCapability
from ingestion.schemas.common import NonBooleanFloat, StrictModel


class ProviderUsage(StrictModel):
    provider: str = Field(min_length=1)
    capability: ProviderCapability
    document_id: str = Field(min_length=1)
    credits: NonBooleanFloat = Field(ge=0.0)
    elapsed_seconds: NonBooleanFloat = Field(ge=0.0)


class UsageLedger(Protocol):
    def record(self, usage: ProviderUsage) -> None: ...
