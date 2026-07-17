from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ingestion.schemas.common import (
    BBox,
    ConfidenceMetric,
    DocumentField,
    Evidence,
    MeasuredValue,
    NonBooleanFloat,
    NormalizationAction,
    Observation,
    PageBlock,
    RelativePosixPath,
    RemovedSpan,
    StrictModel,
)


SchemaVersion = Literal["2.0"]
ExtractionMethod = Literal["markdown", "pdf_digital", "ocr", "hybrid"]
ProcessingStatus = Literal["pending", "processed", "failed", "needs_review"]
DocumentType = Literal[
    "manual",
    "formulario",
    "politica",
    "reglamento",
    "programa",
    "matriz",
    "procedimiento",
    "anexo",
    "instructivo",
    "capacitacion",
    "acta",
    "norma",
    "guia",
    "informacion_general",
    "otro",
]


class PageRecord(StrictModel):
    page_number: int = Field(ge=1)
    text_raw: str
    text_normalized: str
    extraction_method: ExtractionMethod
    blocks: list[PageBlock] = Field(default_factory=list)
    removed_spans: list[RemovedSpan] = Field(default_factory=list)
    normalization_actions: list[NormalizationAction] = Field(default_factory=list)
    ocr_confidence: ConfidenceMetric
    warnings: list[str] = Field(default_factory=list)


class PagesArtifact(StrictModel):
    schema_version: SchemaVersion
    document_id: str = Field(min_length=1)
    page_count: int = Field(ge=0)
    pages: list[PageRecord]

    @model_validator(mode="after")
    def validate_page_count(self) -> "PagesArtifact":
        if self.page_count != len(self.pages):
            raise ValueError("page_count must equal the number of pages")
        return self


class OcrWord(StrictModel):
    text: str
    bbox: BBox
    confidence: Optional[NonBooleanFloat] = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class OcrPage(StrictModel):
    page_number: int = Field(ge=1)
    words: list[OcrWord] = Field(default_factory=list)
    confidence: ConfidenceMetric
    word_count: int = Field(ge=0)
    low_confidence_word_count: Optional[int] = Field(default=None, ge=0)
    deskew: Observation
    rotation: MeasuredValue
    handwriting: Observation
    warnings: list[str] = Field(default_factory=list)


class OcrArtifact(StrictModel):
    schema_version: SchemaVersion
    document_id: str = Field(min_length=1)
    engine: Optional[str] = None
    engine_version: Optional[str] = None
    language: Optional[str] = None
    document_confidence: ConfidenceMetric
    pages: list[OcrPage]
    warnings: list[str] = Field(default_factory=list)


class TableCell(StrictModel):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    bbox: Optional[BBox] = None
    warnings: list[str] = Field(default_factory=list)


class TableRecord(StrictModel):
    table_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    bbox: Optional[BBox]
    caption: Optional[str] = None
    headers: list[str] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    markdown_representation: str
    extractor: str = Field(min_length=1)
    quality: ConfidenceMetric
    warnings: list[str] = Field(default_factory=list)


class TablesArtifact(StrictModel):
    schema_version: SchemaVersion
    document_id: str = Field(min_length=1)
    table_count: int = Field(ge=0)
    tables: list[TableRecord]
    page_observations: list[Observation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_table_count(self) -> "TablesArtifact":
        if self.table_count != len(self.tables):
            raise ValueError("table_count must equal the number of tables")
        return self


class FormLabel(StrictModel):
    label_id: str = Field(min_length=1)
    text: str
    bbox: Optional[BBox] = None
    warnings: list[str] = Field(default_factory=list)


class FormControl(StrictModel):
    control_id: str = Field(min_length=1)
    control_type: Literal[
        "text",
        "checkbox",
        "radio",
        "selection",
        "signature",
        "blank_area",
        "other",
    ]
    bbox: BBox
    label_id: Optional[str] = None
    value: Optional[str] = None
    selected: Optional[bool] = None
    warnings: list[str] = Field(default_factory=list)


class FormGroup(StrictModel):
    group_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    bbox: Optional[BBox] = None
    title: Optional[str] = None
    labels: list[FormLabel] = Field(default_factory=list)
    controls: list[FormControl] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FormsArtifact(StrictModel):
    schema_version: SchemaVersion
    document_id: str = Field(min_length=1)
    groups: list[FormGroup] = Field(default_factory=list)
    page_observations: list[Observation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChangeHistoryEntry(StrictModel):
    version: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DocumentControl(StrictModel):
    title: DocumentField
    code: DocumentField
    version: DocumentField
    publication_date: DocumentField
    effective_date: DocumentField
    change_history: list[ChangeHistoryEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Classification(StrictModel):
    document_type: DocumentType
    document_type_confidence: ConfidenceMetric
    topic: str
    subtopic: Optional[str] = None
    topic_confidence: ConfidenceMetric
    signals: list[str] = Field(default_factory=list)
    route_prior: Optional[str] = None
    content_prediction: Optional[str] = None
    conflict_status: str = "none"
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MetadataArtifact(StrictModel):
    schema_version: SchemaVersion
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    normalized_relpath: RelativePosixPath
    legacy_path: Optional[str] = None
    legacy_source_path: Optional[str] = None
    legacy_normalized_path: Optional[str] = None
    document_control: DocumentControl
    classification: Classification
    page_count: int = Field(ge=0)
    language: str = "es"
    extraction_method: ExtractionMethod
    ocr_confidence: ConfidenceMetric
    handwriting: Observation
    tables: Observation
    forms: Observation
    feature_observations: dict[str, Observation] = Field(default_factory=dict)
    source_hash: str
    corpus_version: str
    pipeline_version: str
    processing_status: ProcessingStatus
    review_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat()
    )


class ValidationCheck(BaseModel):
    check: str
    status: Literal["passed", "failed", "warning"]
    details: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    schema_version: str = "1.0"
    run_id: str = "manual"
    status: Literal["passed", "failed"]
    documents_checked: int
    errors: int
    warnings: int = 0
    checks: list[ValidationCheck]
