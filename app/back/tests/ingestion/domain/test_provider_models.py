from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion.domain.models.classification import ClassificationCandidate, ClassificationResult
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.parsed_document import ParsedDocument, ParsedPage
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.schemas.common import Evidence


def _job(capability: str = "parse") -> ProviderJobRef:
    return ProviderJobRef(
        provider="llama_cloud",
        capability=capability,
        job_id="job_123",
        status="completed",
        configuration_hash="sha256:abc123",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
    )


def test_provider_job_ref_serializes_stable_cloud_provenance() -> None:
    job = _job()

    assert job.model_dump(mode="json") == {
        "provider": "llama_cloud",
        "capability": "parse",
        "job_id": "job_123",
        "status": "completed",
        "configuration_hash": "sha256:abc123",
        "created_at": "2026-07-21T00:00:00Z",
        "completed_at": "2026-07-21T00:01:00Z",
    }


def test_provider_job_ref_rejects_unknown_status_and_sdk_objects() -> None:
    with pytest.raises(ValidationError):
        ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="done",
            configuration_hash="sha256:abc123",
            created_at=datetime.now(timezone.utc),
            sdk_response=object(),
        )


def test_parsed_document_requires_contiguous_pages() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        ParsedDocument(
            provider_job=_job(),
            markdown_pages=[
                ParsedPage(page_number=1, markdown="uno"),
                ParsedPage(page_number=3, markdown="tres"),
            ],
            items_pages=[],
            page_metadata=[],
            job_metadata={},
            warnings=[],
        )


def test_classification_result_keeps_traceable_candidates() -> None:
    result = ClassificationResult(
        provider_job=_job("classify"),
        selected=ClassificationCandidate(
            label="formulario",
            confidence=0.93,
            evidence=[
                Evidence(page_number=1, text="Formato de queja y denuncia"),
            ],
            reasoning_summary="Reglas de LlamaClassify apuntan a formulario.",
        ),
        candidates=[],
        warnings=[],
    )

    assert result.selected.label == "formulario"
    assert result.selected.evidence[0].page_number == 1


def test_extraction_result_rejects_critical_fields_without_evidence() -> None:
    with pytest.raises(ValidationError, match="critical"):
        ExtractionResult(
            provider_job=_job("extract"),
            schema_name="document_control",
            fields=[
                ExtractionField(
                    name="code",
                    value="RG.RH-01-SST",
                    confidence=0.88,
                    evidence=[],
                    critical=True,
                )
            ],
            warnings=[],
        )
