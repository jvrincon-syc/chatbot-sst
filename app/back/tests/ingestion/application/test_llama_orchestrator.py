from __future__ import annotations

import asyncio
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


_NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class _RecordingEventLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def event(self, **kwargs) -> None:
        self.events.append(kwargs)


class _FakeParser:
    def __init__(
        self,
        *,
        result: ParsedDocument | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or _parsed_document()
        self.error = error
        self.calls: list[object] = []

    async def parse(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeClassifier:
    def __init__(
        self,
        *results: ClassificationResult,
        error: Exception | None = None,
    ) -> None:
        self._results = list(results)
        self.error = error
        self.calls: list[object] = []

    async def classify(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self._results.pop(0)


class _FakeExtractor:
    def __init__(
        self,
        *,
        result: ExtractionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or _extraction_result()
        self.error = error
        self.calls: list[object] = []

    async def extract(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _provider_job(capability: str, job_id: str) -> ProviderJobRef:
    return ProviderJobRef(
        provider="llama_cloud",
        capability=capability,
        job_id=job_id,
        status="completed",
        configuration_hash=f"sha256:{capability}",
        created_at=_NOW,
        completed_at=_NOW,
    )


def _parsed_document(markdown: str = "# Politica SST\n\nCodigo SST-PO-01") -> ParsedDocument:
    return ParsedDocument(
        provider_job=_provider_job("parse", "pjb_parse"),
        markdown_pages=[ParsedPage(page_number=1, markdown=markdown)],
    )


def _classification_result(label: str, job_id: str) -> ClassificationResult:
    return ClassificationResult(
        provider_job=_provider_job("classify", job_id),
        selected=ClassificationCandidate(
            label=label,
            confidence=0.97,
            evidence=[Evidence(page_number=1, text=label, source="llama_classify")],
        ),
    )


def _extraction_result(
    *,
    value: str = "SST-PO-01",
    evidence_text: str = "SST-PO-01",
) -> ExtractionResult:
    return ExtractionResult(
        provider_job=_provider_job("extract", "pjb_extract"),
        schema_name="politica_document_control",
        fields=[
            ExtractionField(
                name="code",
                value=value,
                critical=True,
                evidence=[Evidence(page_number=1, text=evidence_text, source="llama_extract")],
            )
        ],
    )


def _orchestrator(
    *,
    parser: _FakeParser | None = None,
    classifier: _FakeClassifier | None = None,
    extractor: _FakeExtractor | None = None,
    classify_enabled: bool = False,
    extract_enabled: bool = False,
    call_order: tuple[str, ...] = ("parse",),
    event_logger: _RecordingEventLogger | None = None,
) -> LlamaOrchestrator:
    return LlamaOrchestrator(
        parser=parser or _FakeParser(),
        classifier=classifier,
        extractor=extractor,
        classify_enabled=classify_enabled,
        extract_enabled=extract_enabled,
        call_order=call_order,
        classify_max_pages=3,
        parse_configuration_hash="sha256:parse",
        classification_configuration_hash="sha256:classify",
        extraction_configuration_hash="sha256:extract",
        event_logger=event_logger,
    )


def _run(orchestrator: LlamaOrchestrator):
    return asyncio.run(
        orchestrator.run(
            document_id="doc-1",
            source_path=Path("docs/manual.pdf"),
            source_hash="sha256:source",
            mime_type="application/pdf",
        )
    )


def test_llama_orchestrator_rechaza_extract_antes_de_parse() -> None:
    with pytest.raises(ValueError, match="must run after"):
        _orchestrator(
            extract_enabled=True,
            extractor=_FakeExtractor(),
            call_order=("extract", "parse"),
        )


def test_llama_orchestrator_registra_fallo_de_parse_y_lo_propaga() -> None:
    events = _RecordingEventLogger()
    orchestrator = _orchestrator(
        parser=_FakeParser(error=RuntimeError("parse offline")),
        call_order=("parse",),
        event_logger=events,
    )

    with pytest.raises(RuntimeError, match="parse offline"):
        _run(orchestrator)

    assert [event["event"] for event in events.events] == [
        "llama_parse_start",
        "llama_parse_failed",
    ]
    assert events.events[-1]["status"] == "failed"
    assert events.events[-1]["warning_code"] == "llama_parse_failed"


def test_llama_orchestrator_omite_classify_si_no_hay_classifier_configurado() -> None:
    events = _RecordingEventLogger()
    orchestrator = _orchestrator(
        parser=_FakeParser(),
        classifier=None,
        classify_enabled=True,
        call_order=("parse", "classify"),
        event_logger=events,
    )

    result = _run(orchestrator)

    assert result.understanding.document_type is None
    assert result.understanding.topic is None
    assert result.understanding.warnings == ["llama_classify_disabled"]
    assert [event["event"] for event in events.events] == [
        "llama_parse_start",
        "llama_parse_finished",
        "llama_classify_skipped",
    ]
    assert events.events[-1]["status"] == "skipped"
    assert events.events[-1]["warning_code"] == "llama_classify_disabled"


def test_llama_orchestrator_reporta_warning_cuando_extract_esta_deshabilitado() -> None:
    events = _RecordingEventLogger()
    orchestrator = _orchestrator(
        parser=_FakeParser(),
        extract_enabled=False,
        call_order=("parse", "extract"),
        event_logger=events,
    )

    result = _run(orchestrator)

    assert result.understanding.warnings == ["llama_extract_disabled"]
    assert [event["event"] for event in events.events] == [
        "llama_parse_start",
        "llama_parse_finished",
        "llama_extract_skipped",
    ]
    assert events.events[-1]["status"] == "skipped"


def test_llama_orchestrator_registra_fallo_de_extract_y_lo_propaga() -> None:
    events = _RecordingEventLogger()
    orchestrator = _orchestrator(
        parser=_FakeParser(),
        extractor=_FakeExtractor(error=RuntimeError("extract timeout")),
        extract_enabled=True,
        call_order=("parse", "extract"),
        event_logger=events,
    )

    with pytest.raises(RuntimeError, match="extract timeout"):
        _run(orchestrator)

    assert [event["event"] for event in events.events] == [
        "llama_parse_start",
        "llama_parse_finished",
        "llama_extract_start",
        "llama_extract_failed",
    ]
    assert events.events[-1]["upstream_job_id"] == "pjb_parse"


def test_llama_orchestrator_marca_campos_criticos_no_soportados() -> None:
    events = _RecordingEventLogger()
    orchestrator = _orchestrator(
        parser=_FakeParser(result=_parsed_document(markdown="# Politica SST\n\nCodigo SST-PO-01")),
        extractor=_FakeExtractor(
            result=_extraction_result(value="NO-SOPORTADO", evidence_text="NO-SOPORTADO")
        ),
        extract_enabled=True,
        call_order=("parse", "extract"),
        event_logger=events,
    )

    result = _run(orchestrator)

    assert result.understanding.warnings == [
        "llama_extract_unsupported_critical_field:code"
    ]
    assert events.events[-1]["warning_count"] == 1


def test_llama_orchestrator_ejecuta_classify_y_extract_con_parse_previo() -> None:
    classifier = _FakeClassifier(
        _classification_result("politica", "classify_doc_type"),
        _classification_result("sg_sst", "classify_topic"),
    )
    extractor = _FakeExtractor(result=_extraction_result())
    orchestrator = _orchestrator(
        parser=_FakeParser(),
        classifier=classifier,
        extractor=extractor,
        classify_enabled=True,
        extract_enabled=True,
        call_order=("parse", "classify", "extract"),
    )

    result = _run(orchestrator)

    assert result.understanding.document_type is not None
    assert result.understanding.topic is not None
    assert result.understanding.schema_extract == "politica_document_control"
    assert classifier.calls[0].parse_job_id == "pjb_parse"
    assert extractor.calls[0].parse_job_id == "pjb_parse"
