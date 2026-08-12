"""Contratos de los catálogos físicos auditables de documentos por proyecto."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from ingestion.schemas.common import StrictModel
from rag_platform.domain.models import ProcessingOrigin


_PROJECT_ID_PATTERN = r"^proj_[a-z0-9][a-z0-9-]{0,127}$"
_SOURCE_DOCUMENT_ID_PATTERN = r"^sdoc_[a-z0-9][a-z0-9-]{0,127}$"
_REVISION_ID_PATTERN = r"^srev_[a-z0-9][a-z0-9-]{0,127}$"
_PROCESSING_PROFILE_ID_PATTERN = r"^pp_[a-z0-9][a-z0-9-]{0,127}$"
_RAG_VARIANT_ID_PATTERN = r"^ragv_[a-z0-9][a-z0-9-]{0,127}$"
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"


class PlatformArtifactProvenance(StrictModel):
    """Auditoría semántica opcional; no participa en la identidad física."""

    rag_variant_id: str | None = Field(default=None, pattern=_RAG_VARIANT_ID_PATTERN)
    semantic_recipe_fingerprint: str | None = Field(
        default=None, pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_complete_semantic_provenance(self) -> "PlatformArtifactProvenance":
        if (self.rag_variant_id is None) != (self.semantic_recipe_fingerprint is None):
            raise ValueError(
                "rag_variant_id and semantic_recipe_fingerprint must be set together"
            )
        return self


class RawDocumentArtifactRecord(StrictModel):
    """Fila del catálogo físico ``project_raw_document_artifacts``."""

    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    source_document_revision_id: str = Field(pattern=_REVISION_ID_PATTERN)
    logical_document_id: str = Field(pattern=_SOURCE_DOCUMENT_ID_PATTERN)
    artifact_relpath: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    raw_content_hash: str = Field(pattern=_FINGERPRINT_PATTERN)
    file_size: int = Field(ge=0)
    uploaded_by: str = Field(min_length=1)
    uploaded_at: datetime


class NormalizedDocumentArtifactRecord(StrictModel):
    """Fila física que acompaña al catálogo lógico de normalizados.

    La identidad sigue siendo proyecto, revisión y fingerprint de procesamiento;
    la provenance semántica solo conserva el contexto de quien la produjo.
    """

    normalized_document_id: str = Field(min_length=1)
    project_id: str = Field(pattern=_PROJECT_ID_PATTERN)
    source_document_revision_id: str = Field(pattern=_REVISION_ID_PATTERN)
    logical_document_id: str = Field(pattern=_SOURCE_DOCUMENT_ID_PATTERN)
    processing_profile_id: str = Field(pattern=_PROCESSING_PROFILE_ID_PATTERN)
    processing_profile_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)
    processing_origin: ProcessingOrigin
    parser_provider: str = Field(min_length=1)
    parser_engine: str = Field(min_length=1)
    observed_revision: str = Field(min_length=1)
    sanitized_config_json: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(min_length=1)
    markdown_relpath: str = Field(min_length=1)
    metadata_relpath: str = Field(min_length=1)
    pages_relpath: str = Field(min_length=1)
    tables_relpath: str = Field(min_length=1)
    forms_relpath: str = Field(min_length=1)
    source_hash: str = Field(pattern=_FINGERPRINT_PATTERN)
    processing_status: Literal["processed", "needs_review"]
    rag_variant_id: str | None = Field(default=None, pattern=_RAG_VARIANT_ID_PATTERN)
    semantic_recipe_fingerprint: str | None = Field(
        default=None, pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_complete_semantic_provenance(self) -> "NormalizedDocumentArtifactRecord":
        if (self.rag_variant_id is None) != (self.semantic_recipe_fingerprint is None):
            raise ValueError(
                "rag_variant_id and semantic_recipe_fingerprint must be set together"
            )
        return self
