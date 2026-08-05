from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ingestion.domain.models.provider import ProviderJobRef
from ingestion.schemas.common import Evidence, NonBooleanFloat, StrictModel


class ExtractionField(StrictModel):
    name: str = Field(min_length=1)
    value: Any
    confidence: NonBooleanFloat | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    critical: bool = False
    warnings: list[str] = Field(default_factory=list)


class ExtractionResult(StrictModel):
    provider_job: ProviderJobRef
    schema_name: str = Field(min_length=1)
    fields: list[ExtractionField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_critical_fields_have_evidence(self) -> "ExtractionResult":
        missing = [field.name for field in self.fields if field.critical and not field.evidence]
        if missing:
            raise ValueError(f"critical fields require evidence: {', '.join(missing)}")
        return self
