from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import Field

from ingestion.domain.models.classification import ClassificationResult
from ingestion.schemas.common import StrictModel


class ClassificationRequest(StrictModel):
    document_id: str = Field(min_length=1)
    source_path: Path
    labels: tuple[str, ...]
    max_pages: int | None = Field(default=None, ge=1)
    configuration_hash: str = Field(min_length=1)


class DocumentClassifierPort(Protocol):
    async def classify(self, request: ClassificationRequest) -> ClassificationResult: ...
