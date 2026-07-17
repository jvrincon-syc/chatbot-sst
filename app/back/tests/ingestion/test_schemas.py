import pytest
from pydantic import ValidationError

from ingestion.schemas.artifacts import PageRecord, PagesArtifact
from ingestion.schemas.common import ConfidenceMetric
from ingestion.schemas.loader import load_artifact


def test_artifact_schemas_accept_valid_minimal_canonical_contracts() -> None:
    pages = PagesArtifact(
        schema_version="2.0",
        document_id="doc_123",
        page_count=1,
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Texto",
                text_normalized="Texto",
                extraction_method="markdown",
                ocr_confidence=ConfidenceMetric(
                    kind="unavailable",
                    value=None,
                ),
            )
        ],
    )

    assert pages.schema_version == "2.0"
    assert pages.pages[0].ocr_confidence.kind == "unavailable"


def test_legacy_pages_are_read_through_the_explicit_adapter() -> None:
    pages = load_artifact(
        {
            "schema_version": "1.0",
            "document_id": "doc_123",
            "page_count": 1,
            "pages": [
                {
                    "page_number": 1,
                    "text_raw": "Texto",
                    "text_normalized": "Texto",
                    "extraction_method": "ocr",
                    "ocr_confidence": 0.8,
                }
            ],
        },
        "pages",
        {},
    )

    assert pages.schema_version == "2.0"
    assert pages.pages[0].ocr_confidence.kind == "estimated"


def test_confidence_values_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        ConfidenceMetric(
            kind="estimated",
            value=1.5,
            method="test_proxy",
        )
