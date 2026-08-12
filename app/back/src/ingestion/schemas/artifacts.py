from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

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
ExtractionMethod = Literal["markdown", "pdf_digital", "ocr", "hybrid", "llamaparse", "hybrid_llamaparse"]
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


class LlamaCloudMetadata(StrictModel):
    parse_job_id: str = Field(min_length=1)
    parse_status: Literal["pending", "running", "completed", "failed", "cancelled"]
    parse_configuration_hash: str = Field(min_length=1)
    page_metadata: list[dict[str, Any]] = Field(default_factory=list)
    job_metadata: dict[str, Any] = Field(default_factory=dict)
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


# Patrones de identidad de plataforma (ADR-006). Se validan como localizadores
# tipados; la autoridad de identidad es ``rag_platform.domain.identity``, que NO
# se importa aquí para no acoplar la lane legacy de ingestion al módulo nuevo.
_PLATFORM_PROJECT_ID_PATTERN = r"^proj_[a-z0-9][a-z0-9-]{0,127}$"
_PLATFORM_SOURCE_DOCUMENT_ID_PATTERN = r"^sdoc_[a-z0-9][a-z0-9-]{0,127}$"
_PLATFORM_REVISION_ID_PATTERN = r"^srev_[a-z0-9][a-z0-9-]{0,127}$"
_PLATFORM_PROCESSING_PROFILE_ID_PATTERN = r"^pp_[a-z0-9][a-z0-9-]{0,127}$"
_PLATFORM_RAG_VARIANT_ID_PATTERN = r"^ragv_[a-z0-9][a-z0-9-]{0,127}$"
_PLATFORM_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"


class PlatformArtifactProvenance(StrictModel):
    """Optional semantic audit provenance shared by platform artifacts."""

    rag_variant_id: Optional[str] = Field(default=None, pattern=_PLATFORM_RAG_VARIANT_ID_PATTERN)
    semantic_recipe_fingerprint: Optional[str] = Field(
        default=None, pattern=_PLATFORM_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_complete_semantic_provenance(self) -> "PlatformArtifactProvenance":
        if (self.rag_variant_id is None) != (self.semantic_recipe_fingerprint is None):
            raise ValueError(
                "rag_variant_id and semantic_recipe_fingerprint must be set together"
            )
        return self


class PlatformDocumentIdentity(StrictModel):
    """Identidad de plataforma opcional para artefactos Schema 2.0 nuevos (ADR-006).

    Es **aditiva**: los artefactos legacy SST no la emiten, por lo que
    ``MetadataArtifact.platform_identity`` queda ``None`` y validan sin cambios
    (ese ``None`` es el adaptador Schema 2.0 legacy). Cuando el pipeline de
    plataforma produce un normalizado, la puebla para ligar el artefacto a
    proyecto + revisión + receta, sin depender solo de ``source_relpath``
    (plan §Fase 2, §4.4).

    ``normalized_document_id`` es opcional porque su generador con prefijo llega
    en una fase posterior; su identidad lógica ya la fijan ``project_id +
    source_document_revision_id + processing_profile_fingerprint``.
    """

    project_id: str = Field(pattern=_PLATFORM_PROJECT_ID_PATTERN)
    source_document_id: str = Field(pattern=_PLATFORM_SOURCE_DOCUMENT_ID_PATTERN)
    source_document_revision_id: str = Field(pattern=_PLATFORM_REVISION_ID_PATTERN)
    normalized_document_id: Optional[str] = Field(default=None, min_length=1)
    processing_profile_id: str = Field(pattern=_PLATFORM_PROCESSING_PROFILE_ID_PATTERN)
    processing_profile_fingerprint: str = Field(pattern=_PLATFORM_FINGERPRINT_PATTERN)
    provenance: PlatformArtifactProvenance = Field(default_factory=PlatformArtifactProvenance)
    schema_version: SchemaVersion = "2.0"

    @model_validator(mode="before")
    @classmethod
    def migrate_flat_provenance(cls, value: Any) -> Any:
        """Migrate historical flat provenance without accepting ambiguity."""

        if not isinstance(value, dict):
            return value
        flat_keys = ("rag_variant_id", "semantic_recipe_fingerprint")
        flat = {key: value[key] for key in flat_keys if key in value}
        if not flat:
            return value

        normalized = dict(value)
        nested = normalized.get("provenance")
        if nested is None:
            normalized["provenance"] = flat
        elif not isinstance(nested, dict):
            return normalized
        else:
            if any(nested.get(key) != field_value for key, field_value in flat.items()):
                raise ValueError("conflicting flat and nested provenance")
        for key in flat_keys:
            normalized.pop(key, None)
        return normalized

    @property
    def rag_variant_id(self) -> Optional[str]:
        """Expose semantic audit provenance without making it identity."""

        return self.provenance.rag_variant_id

    @property
    def semantic_recipe_fingerprint(self) -> Optional[str]:
        """Expose semantic audit provenance without making it identity."""

        return self.provenance.semantic_recipe_fingerprint


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
    llama_cloud: Optional[LlamaCloudMetadata] = None
    source_hash: str
    corpus_version: str
    pipeline_version: str
    processing_status: ProcessingStatus
    review_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Aditivo (ADR-006): identidad de plataforma para normalizados nuevos. Los
    # artefactos legacy SST lo dejan en None y validan igual.
    platform_identity: Optional[PlatformDocumentIdentity] = None
    # Aditivo: provenance semántica auditable (variante + receta) como bloque
    # separado de la identidad. Nullable: la lane legacy lo deja en None.
    platform_provenance: Optional[PlatformArtifactProvenance] = None
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
