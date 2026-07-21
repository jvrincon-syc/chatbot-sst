from __future__ import annotations

from pydantic import Field

from ingestion.domain.models.provider import ProviderJobRef
from ingestion.schemas.common import Evidence, NonBooleanFloat, StrictModel


class ClassificationCandidate(StrictModel):
    label: str = Field(min_length=1)
    confidence: NonBooleanFloat = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ClassificationResult(StrictModel):
    provider_job: ProviderJobRef
    selected: ClassificationCandidate
    candidates: list[ClassificationCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
