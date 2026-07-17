from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ingestion.schemas.artifacts import (
    FormsArtifact,
    OcrArtifact,
    PageRecord,
    TablesArtifact,
)


class ReadResult(BaseModel):
    extraction_method: str
    markdown: str
    pages: List[PageRecord]
    warnings: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    tables: Optional[TablesArtifact] = None
    forms: Optional[FormsArtifact] = None
    ocr: Optional[OcrArtifact] = None

    @property
    def page_count(self) -> int:
        return len(self.pages)
