from __future__ import annotations

import inspect
from pathlib import Path

from ingestion.application.ports.classifier import ClassificationRequest, DocumentClassifierPort
from ingestion.application.ports.extractor import ExtractionRequest, StructuredExtractorPort
from ingestion.application.ports.parser import DocumentParserPort, ParseRequest
from ingestion.application.ports.provider_errors import ProviderTimeoutError
from ingestion.application.ports.provider_run_repository import ProviderRunRepository
from ingestion.application.ports.usage_ledger import ProviderUsage, UsageLedger


def test_ports_expose_small_async_capability_methods() -> None:
    assert inspect.iscoroutinefunction(DocumentParserPort.parse)
    assert inspect.iscoroutinefunction(DocumentClassifierPort.classify)
    assert inspect.iscoroutinefunction(StructuredExtractorPort.extract)


def test_requests_are_typed_and_do_not_require_sdk_objects() -> None:
    parse_request = ParseRequest(
        document_id="doc_123",
        source_path=Path("data/docs_raw/manual.pdf"),
        source_hash="sha256:source",
        mime_type="application/pdf",
        configuration_hash="sha256:config",
    )
    classification_request = ClassificationRequest(
        document_id=parse_request.document_id,
        source_path=parse_request.source_path,
        labels=("manual", "formulario"),
        max_pages=5,
        configuration_hash=parse_request.configuration_hash,
    )
    extraction_request = ExtractionRequest(
        document_id=parse_request.document_id,
        schema_name="document_control",
        parse_job_id="job_123",
        configuration_hash=parse_request.configuration_hash,
    )

    assert parse_request.source_path.suffix == ".pdf"
    assert classification_request.labels == ("manual", "formulario")
    assert extraction_request.parse_job_id == "job_123"


def test_repository_and_ledger_ports_are_narrow_protocols() -> None:
    assert hasattr(ProviderRunRepository, "save")
    assert hasattr(ProviderRunRepository, "get")
    assert hasattr(UsageLedger, "record")

    usage = ProviderUsage(
        provider="llama_cloud",
        capability="parse",
        document_id="doc_123",
        credits=3.5,
        elapsed_seconds=12.0,
    )

    assert usage.credits == 3.5
    assert issubclass(ProviderTimeoutError, TimeoutError)
