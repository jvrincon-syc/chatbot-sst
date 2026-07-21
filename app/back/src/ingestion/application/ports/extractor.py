from __future__ import annotations

from typing import Protocol

from pydantic import Field

from ingestion.domain.models.extraction import ExtractionResult
from ingestion.schemas.common import StrictModel


class ExtractionRequest(StrictModel):
    document_id: str = Field(min_length=1)
    schema_name: str = Field(min_length=1)
    parse_job_id: str | None = None
    file_id: str | None = None
    configuration_hash: str = Field(min_length=1)


class StructuredExtractorPort(Protocol):
    async def extract(self, request: ExtractionRequest) -> ExtractionResult: ...
