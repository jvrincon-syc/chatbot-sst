from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class InventoryRecord(BaseModel):
    document_id: str
    source_path: str
    document_name: str
    detected_extension: Optional[str]
    reported_extension: Optional[str]
    mime_type: str
    content_hash: str
    file_size: int = Field(ge=0)
    ingestion_date: str
    category_inferred: str
    document_version: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=0)
    processing_status: Literal["pending", "processed", "failed", "needs_review", "skipped"] = "pending"
    pipeline_version: str
    corpus_version: str
