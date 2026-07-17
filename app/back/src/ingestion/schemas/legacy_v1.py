from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ingestion.schemas.common import NonBooleanFloat


class LegacyModel(BaseModel):
    """Permissive reader models for the historic schema 1.0 payloads."""

    model_config = ConfigDict(extra="allow")


class LegacyPageRecord(LegacyModel):
    page_number: int = Field(ge=1)
    text_raw: str
    text_normalized: str
    extraction_method: Literal["markdown", "pdf_digital", "ocr"]
    ocr_confidence: Optional[NonBooleanFloat] = Field(
        default=None, ge=0.0, le=1.0
    )
    has_handwriting_warning: bool = False
    warnings: list[str] = Field(default_factory=list)


class LegacyPagesArtifact(LegacyModel):
    schema_version: Literal["1.0"]
    document_id: str
    page_count: int = Field(ge=0)
    pages: list[LegacyPageRecord]


class LegacyOcrPage(LegacyModel):
    page_number: int = Field(ge=1)
    confidence: Optional[NonBooleanFloat] = Field(default=None, ge=0.0, le=1.0)
    word_count: int = Field(ge=0)
    low_confidence_word_count: Optional[int] = Field(default=None, ge=0)
    deskew_applied: bool = False
    rotation_detected_degrees: Optional[NonBooleanFloat] = None
    contains_handwriting: Optional[bool] = None
    warnings: list[str] = Field(default_factory=list)


class LegacyOcrArtifact(LegacyModel):
    schema_version: Literal["1.0"]
    document_id: str
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    language: Optional[str] = None
    overall_confidence: Optional[NonBooleanFloat] = Field(
        default=None, ge=0.0, le=1.0
    )
    pages: list[LegacyOcrPage]


class LegacyTableRecord(LegacyModel):
    table_id: str
    page_number: int = Field(ge=1)
    caption: Optional[str] = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    markdown_representation: str
    quality: Optional[NonBooleanFloat] = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class LegacyTablesArtifact(LegacyModel):
    schema_version: Literal["1.0"]
    document_id: str
    table_count: int = Field(ge=0)
    tables: list[LegacyTableRecord]


class LegacyMetadataArtifact(LegacyModel):
    schema_version: Literal["1.0"]
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
    extraction_method: Literal["markdown", "pdf_digital", "ocr"]
    ocr_engine: Optional[str] = None
    ocr_confidence: Optional[NonBooleanFloat] = Field(
        default=None, ge=0.0, le=1.0
    )
    contains_handwriting: Optional[bool] = None
    contains_tables: Optional[bool] = None
    classification_confidence: Optional[NonBooleanFloat] = Field(
        default=None, ge=0.0, le=1.0
    )
    content_hash: str
    corpus_version: str
    pipeline_version: str
    processing_status: Literal[
        "pending", "processed", "failed", "needs_review", "skipped"
    ]
    warnings: list[str] = Field(default_factory=list)
    processed_at: Optional[str] = None


class LegacyInventoryRecord(LegacyModel):
    schema_version: Literal["1.0"]
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
    processing_status: Literal[
        "pending", "processed", "failed", "needs_review", "skipped"
    ] = "pending"
    pipeline_version: str
    corpus_version: str
