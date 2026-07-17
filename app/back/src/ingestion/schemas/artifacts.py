from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ExtractionMethod = Literal["markdown", "pdf_digital", "ocr"]
ProcessingStatus = Literal["pending", "processed", "failed", "needs_review", "skipped"]


class PageRecord(BaseModel):
    page_number: int = Field(ge=1)
    text_raw: str
    text_normalized: str
    extraction_method: ExtractionMethod
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    has_handwriting_warning: bool = False
    warnings: List[str] = Field(default_factory=list)


class PagesArtifact(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    page_count: int = Field(ge=0)
    pages: List[PageRecord]


class OcrPage(BaseModel):
    page_number: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    word_count: int = Field(ge=0)
    low_confidence_word_count: int = Field(ge=0)
    deskew_applied: bool
    rotation_detected_degrees: int
    contains_handwriting: bool
    warnings: List[str] = Field(default_factory=list)


class OcrArtifact(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    engine: str
    engine_version: str
    language: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    pages: List[OcrPage]


class TableRecord(BaseModel):
    table_id: str
    page_number: int = Field(ge=1)
    caption: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown_representation: str
    quality: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)


class TablesArtifact(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    table_count: int = Field(ge=0)
    tables: List[TableRecord]


class MetadataArtifact(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    document_name: str
    source_path: str
    normalized_path: str
    document_type: str
    topic: str
    subtopic: Optional[str] = None
    version: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    page_count: int = Field(ge=0)
    language: str = "es"
    extraction_method: ExtractionMethod
    ocr_engine: Optional[str] = None
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    contains_handwriting: bool = False
    contains_tables: bool = False
    classification_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    content_hash: str
    corpus_version: str
    pipeline_version: str
    processing_status: ProcessingStatus
    warnings: List[str] = Field(default_factory=list)
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat())


class ValidationCheck(BaseModel):
    check: str
    status: Literal["passed", "failed", "warning"]
    details: List[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    schema_version: str = "1.0"
    run_id: str = "manual"
    status: Literal["passed", "failed"]
    documents_checked: int
    errors: int
    warnings: int = 0
    checks: List[ValidationCheck]
