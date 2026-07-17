import pytest
from pydantic import ValidationError

from ingestion.schemas.artifacts import (
    MetadataArtifact,
    OcrArtifact,
    OcrPage,
    PageRecord,
    PagesArtifact,
)


def test_artifact_schemas_accept_valid_minimal_contracts() -> None:
    metadata = MetadataArtifact(
        document_id="doc_123",
        document_name="manual.md",
        source_path="data/docs_raw/manual.md",
        normalized_path="data/docs_normalized/manual.md",
        document_type="manual",
        topic="SST",
        page_count=1,
        extraction_method="markdown",
        content_hash="abc",
        corpus_version="test",
        pipeline_version="1.0.0",
        processing_status="processed",
    )
    pages = PagesArtifact(
        document_id="doc_123",
        page_count=1,
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Texto",
                text_normalized="Texto",
                extraction_method="markdown",
            )
        ],
    )
    ocr = OcrArtifact(
        document_id="doc_123",
        engine="mock",
        engine_version="0",
        language="spa",
        overall_confidence=0.87,
        pages=[
            OcrPage(
                page_number=1,
                confidence=0.87,
                word_count=10,
                low_confidence_word_count=1,
                deskew_applied=False,
                rotation_detected_degrees=0,
                contains_handwriting=False,
            )
        ],
    )

    assert metadata.schema_version == "1.0"
    assert pages.pages[0].ocr_confidence is None
    assert ocr.pages[0].confidence == 0.87


def test_confidence_values_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        PageRecord(
            page_number=1,
            text_raw="Texto",
            text_normalized="Texto",
            extraction_method="ocr",
            ocr_confidence=1.5,
        )
