from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_platform.domain.artifact_catalog import (
    NormalizedDocumentArtifactRecord,
    PlatformArtifactProvenance,
    RawDocumentArtifactRecord,
)


def test_normalized_artifact_record_exige_provenance_de_procesamiento() -> None:
    record = NormalizedDocumentArtifactRecord.model_validate(
        {
            "normalized_document_id": "ndoc_1234",
            "project_id": "proj_sst-general",
            "source_document_revision_id": "srev_1234",
            "logical_document_id": "sdoc_1234",
            "processing_profile_id": "pp_local-pdf",
            "processing_profile_fingerprint": "a" * 64,
            "processing_origin": "local",
            "parser_provider": "local",
            "parser_engine": "pdfium+tesseract",
            "observed_revision": "2026.08.12",
            "sanitized_config_json": {},
            "schema_version": "2.0",
            "markdown_relpath": "general/doc.md",
            "metadata_relpath": "general/doc.metadata.json",
            "pages_relpath": "general/doc.pages.json",
            "tables_relpath": "general/doc.tables.json",
            "forms_relpath": "general/doc.forms.json",
            "source_hash": "b" * 64,
            "processing_status": "processed",
        }
    )

    assert record.rag_variant_id is None
    assert record.semantic_recipe_fingerprint is None


def test_raw_artifact_record_preserva_la_identidad_logica_y_el_sidecar_fisico() -> None:
    record = RawDocumentArtifactRecord.model_validate(
        {
            "project_id": "proj_sst-general",
            "source_document_revision_id": "srev_1234",
            "logical_document_id": "sdoc_1234",
            "artifact_relpath": "raw/general/doc.pdf",
            "source_relpath": "general/doc.pdf",
            "raw_content_hash": "a" * 64,
            "file_size": 42,
            "uploaded_by": "operator",
            "uploaded_at": "2026-08-12T00:00:00Z",
        }
    )

    assert record.logical_document_id == "sdoc_1234"
    assert record.artifact_relpath == "raw/general/doc.pdf"


def test_platform_provenance_exige_variant_y_recipe_juntas() -> None:
    with pytest.raises(ValidationError):
        PlatformArtifactProvenance.model_validate({"rag_variant_id": "ragv_local-bge"})
