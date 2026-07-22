from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.application.services.llama_orchestrator import LlamaOrchestrator
from ingestion.domain.models.classification import (
    ClassificationCandidate,
    ClassificationResult,
)
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.parsed_document import ParsedDocument, ParsedPage
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.schemas.common import Evidence


def _job(capability: str, job_id: str) -> ProviderJobRef:
    now = datetime.now(timezone.utc)
    return ProviderJobRef(
        provider="llama_cloud",
        capability=capability,
        job_id=job_id,
        status="completed",
        configuration_hash="sha256:config",
        created_at=now,
        completed_at=now,
    )


class RecordingClassifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, tuple[str, ...]]] = []

    async def classify(self, request):
        self.calls.append((request.parse_job_id, request.labels))
        label = "formulario" if "formulario" in request.labels else "convivencia_laboral"
        return ClassificationResult(
            provider_job=_job("classify", f"classify_{len(self.calls)}"),
            selected=ClassificationCandidate(
                label=label,
                confidence=0.94,
                evidence=[Evidence(page_number=1, text=label, source="llama_classify")],
                reasoning_summary="Evidencia visible en el documento.",
            ),
        )


class RecordingParser:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def parse(self, request):
        self.calls.append(request.document_id)
        return ParsedDocument(
            provider_job=_job("parse", "pjb_123"),
            markdown_pages=[
                ParsedPage(page_number=1, markdown="# Formato\n\nCodigo RE.RH-04 SST")
            ],
        )


class RecordingExtractor:
    def __init__(self, *, value: str = "RE.RH-04 SST") -> None:
        self.calls: list[tuple[str | None, str]] = []
        self.value = value

    async def extract(self, request):
        self.calls.append((request.parse_job_id, request.schema_name))
        return ExtractionResult(
            provider_job=_job("extract", "extract_1"),
            schema_name=request.schema_name,
            fields=[
                ExtractionField(
                    name="code",
                    value=self.value,
                    critical=True,
                    evidence=[Evidence(page_number=1, text=self.value, source="llama_extract")],
                )
            ],
        )


class FailingExtractor:
    async def extract(self, _request):
        raise RuntimeError("extract provider failed")


class RecordingEventLogger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def event(self, **kwargs) -> None:
        self.events.append(kwargs)


@pytest.mark.anyio
async def test_llama_orchestrator_can_classify_before_parse_and_extract_after_parse(
    tmp_path: Path,
) -> None:
    parser = RecordingParser()
    classifier = RecordingClassifier()
    extractor = RecordingExtractor()

    result = await LlamaOrchestrator(
        parser=parser,
        classifier=classifier,
        extractor=extractor,
        classify_enabled=True,
        extract_enabled=True,
        call_order=("classify", "parse", "extract"),
        classify_max_pages=5,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
    ).run(
        document_id="doc_123",
        source_path=tmp_path / "form.pdf",
        source_hash="sha256:source",
        mime_type="application/pdf",
    )

    assert classifier.calls[0][0] is None
    assert "formulario" in classifier.calls[0][1]
    assert parser.calls == ["doc_123"]
    assert classifier.calls[1][0] is None
    assert "convivencia_laboral" in classifier.calls[1][1]
    assert extractor.calls == [("pjb_123", "formulario_document_control")]
    assert result.parsed.provider_job.job_id == "pjb_123"
    assert result.understanding.document_type.selected.label == "formulario"
    assert result.understanding.topic.selected.label == "convivencia_laboral"
    assert result.understanding.schema_extract == "formulario_document_control"
    assert result.understanding.extraction.fields[0].name == "code"


@pytest.mark.anyio
async def test_llama_orchestrator_logs_entry_and_exit_for_each_cloud_phase(
    tmp_path: Path,
) -> None:
    event_logger = RecordingEventLogger()

    await LlamaOrchestrator(
        parser=RecordingParser(),
        classifier=RecordingClassifier(),
        extractor=RecordingExtractor(),
        classify_enabled=True,
        extract_enabled=True,
        call_order=("classify", "parse", "extract"),
        classify_max_pages=5,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
        event_logger=event_logger,
    ).run(
        document_id="doc_123",
        source_path=tmp_path / "form.pdf",
        source_hash="sha256:source",
        mime_type="application/pdf",
    )

    assert [
        (event["event"], event["status"], event["capability"], event.get("job_id"))
        for event in event_logger.events
    ] == [
        ("llama_classify_start", "started", "classify", None),
        ("llama_classify_finished", "completed", "classify", "classify_1,classify_2"),
        ("llama_parse_start", "started", "parse", None),
        ("llama_parse_finished", "completed", "parse", "pjb_123"),
        ("llama_extract_start", "started", "extract", None),
        ("llama_extract_finished", "completed", "extract", "extract_1"),
    ]
    assert {event["provider"] for event in event_logger.events} == {"llama_cloud"}
    assert {event["stage"] for event in event_logger.events} == {"llama_cloud"}
    assert {event["document_id"] for event in event_logger.events} == {"doc_123"}
    assert {event["source_path"] for event in event_logger.events} == {
        str(tmp_path / "form.pdf")
    }
    assert [event["level"] for event in event_logger.events] == [
        "info",
        "info",
        "info",
        "info",
        "info",
        "info",
    ]


@pytest.mark.anyio
async def test_llama_orchestrator_can_parse_before_classify_to_reuse_parse_job_id(
    tmp_path: Path,
) -> None:
    classifier = RecordingClassifier()

    result = await LlamaOrchestrator(
        parser=RecordingParser(),
        classifier=classifier,
        extractor=RecordingExtractor(),
        classify_enabled=True,
        extract_enabled=True,
        call_order=("parse", "classify", "extract"),
        classify_max_pages=5,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
    ).run(
        document_id="doc_123",
        source_path=tmp_path / "form.pdf",
        source_hash="sha256:source",
        mime_type="application/pdf",
    )

    assert classifier.calls[0][0] == "pjb_123"
    assert result.understanding.parse_job_id == "pjb_123"


@pytest.mark.anyio
async def test_llama_orchestrator_skips_optional_capabilities_when_disabled(tmp_path: Path) -> None:
    classifier = RecordingClassifier()
    extractor = RecordingExtractor()
    event_logger = RecordingEventLogger()

    result = await LlamaOrchestrator(
        parser=RecordingParser(),
        classifier=classifier,
        extractor=extractor,
        classify_enabled=False,
        extract_enabled=False,
        call_order=("classify", "parse", "extract"),
        classify_max_pages=5,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
        event_logger=event_logger,
    ).run(
        document_id="doc_123",
        source_path=tmp_path / "manual.pdf",
        source_hash="sha256:source",
        mime_type="application/pdf",
    )

    assert classifier.calls == []
    assert extractor.calls == []
    assert result.understanding.schema_extract is None
    assert result.understanding.warnings == ["llama_classify_disabled", "llama_extract_disabled"]
    assert [
        (event["event"], event["status"], event["level"])
        for event in event_logger.events
        if event["status"] == "skipped"
    ] == [
        ("llama_classify_skipped", "skipped", "warning"),
        ("llama_extract_skipped", "skipped", "warning"),
    ]


@pytest.mark.anyio
async def test_llama_orchestrator_logs_provider_failures_as_error(
    tmp_path: Path,
) -> None:
    event_logger = RecordingEventLogger()

    with pytest.raises(RuntimeError, match="extract provider failed"):
        await LlamaOrchestrator(
            parser=RecordingParser(),
            classifier=RecordingClassifier(),
            extractor=FailingExtractor(),
            classify_enabled=True,
            extract_enabled=True,
            call_order=("parse", "classify", "extract"),
            classify_max_pages=5,
            parse_configuration_hash="sha256:parse",
            classification_configuration_hash="sha256:classify",
            extraction_configuration_hash="sha256:extract",
            event_logger=event_logger,
        ).run(
            document_id="doc_123",
            source_path=tmp_path / "manual.pdf",
            source_hash="sha256:source",
            mime_type="application/pdf",
        )

    failed = event_logger.events[-1]
    assert failed["event"] == "llama_extract_failed"
    assert failed["status"] == "failed"
    assert failed["level"] == "error"
    assert failed["capability"] == "extract"
    assert failed["warning_code"] == "llama_extract_failed"
    assert isinstance(failed["exception"], RuntimeError)


@pytest.mark.anyio
async def test_llama_orchestrator_warns_when_critical_extract_value_is_not_supported(
    tmp_path: Path,
) -> None:
    result = await LlamaOrchestrator(
        parser=RecordingParser(),
        classifier=RecordingClassifier(),
        extractor=RecordingExtractor(value="NO-SOPORTADO"),
        classify_enabled=True,
        extract_enabled=True,
        call_order=("parse", "classify", "extract"),
        classify_max_pages=5,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
    ).run(
        document_id="doc_123",
        source_path=tmp_path / "form.pdf",
        source_hash="sha256:source",
        mime_type="application/pdf",
    )

    assert "llama_extract_unsupported_critical_field:code" in result.understanding.warnings


def test_llama_orchestrator_rejects_classify_after_extract_when_both_are_enabled() -> None:
    with pytest.raises(ValueError, match="LlamaClassify must run before LlamaExtract"):
        LlamaOrchestrator(
            parser=RecordingParser(),
            classifier=RecordingClassifier(),
            extractor=RecordingExtractor(),
            classify_enabled=True,
            extract_enabled=True,
            call_order=("parse", "extract", "classify"),
            classify_max_pages=5,
            parse_configuration_hash="sha256:parse",
            classification_configuration_hash="sha256:classify",
            extraction_configuration_hash="sha256:extract",
        )
