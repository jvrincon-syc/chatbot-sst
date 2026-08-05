from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from ingestion.schemas.common import ConfidenceMetric
from ingestion.schemas.common import RelativePosixPath, StrictModel


class InventoryRecord(StrictModel):
    schema_version: Literal["2.0"]
    identity_version: Literal["relpath-posix-v1"] = "relpath-posix-v1"
    document_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    legacy_path: Optional[str] = None
    document_name: str = Field(min_length=1)
    detected_extension: Optional[str]
    reported_extension: Optional[str]
    mime_type: str
    content_hash: str
    file_size: int = Field(ge=0)
    ingestion_date: str
    category_inferred: str
    document_version: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=0)
    ocr_confidence: Optional[ConfidenceMetric] = None
    processing_status: Literal[
        "pending", "processed", "failed", "needs_review"
    ] = "pending"
    pipeline_version: str
    corpus_version: str
    warnings: list[str] = Field(default_factory=list)
