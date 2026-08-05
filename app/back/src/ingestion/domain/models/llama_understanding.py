from __future__ import annotations

from pydantic import Field

from ingestion.domain.models.classification import ClassificationResult
from ingestion.domain.models.extraction import ExtractionResult
from ingestion.domain.models.parsed_document import ParsedDocument
from ingestion.schemas.common import StrictModel


class LlamaUnderstanding(StrictModel):
    parse_job_id: str = Field(min_length=1)
    document_type: ClassificationResult | None = None
    topic: ClassificationResult | None = None
    schema_extract: str | None = None
    extraction: ExtractionResult | None = None
    warnings: list[str] = Field(default_factory=list)


class LlamaPipelineResult(StrictModel):
    parsed: ParsedDocument
    understanding: LlamaUnderstanding
