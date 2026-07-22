from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Literal, Protocol

from core.logging.logger import get_logger
from ingestion.application.ports.classifier import DocumentClassifierPort
from ingestion.application.ports.classifier import ClassificationRequest
from ingestion.application.ports.extractor import ExtractionRequest
from ingestion.application.ports.extractor import StructuredExtractorPort
from ingestion.application.ports.parser import DocumentParserPort, ParseRequest
from ingestion.domain.models.classification import ClassificationResult
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.llama_understanding import LlamaPipelineResult, LlamaUnderstanding
from ingestion.domain.models.parsed_document import ParsedDocument
from ingestion.infrastructure.llama_cloud.classify_rules import (
    classification_labels,
    extraction_schema_for_document_type,
    topic_classification_labels,
)

LlamaStop = Literal["classify", "parse", "extract"]
LlamaLogLevel = Literal["info", "warning", "error"]


class LlamaPhaseEventLogger(Protocol):
    def event(
        self,
        *,
        stage: str,
        event: str,
        status: str,
        message: str,
        level: str | None = None,
        document_id: str | None = None,
        source_path: str | None = None,
        provider: str | None = None,
        capability: str | None = None,
        job_id: str | None = None,
        upstream_job_id: str | None = None,
        configuration_hash: str | None = None,
        result_count: int | None = None,
        warning_count: int | None = None,
        warning_code: str | None = None,
        exception: BaseException | None = None,
    ) -> None:
        """Record a structured provider phase event."""


phase_logger = get_logger(__name__)


class LlamaOrchestrator:
    """Coordinates the configurable Llama Cloud lane.

    `parse` is mandatory for the cloud lane. `classify` and `extract` are
    optional stops controlled by feature flags. `extract` always requires the
    parse job produced by the same lane run.
    """

    def __init__(
        self,
        *,
        parser: DocumentParserPort,
        classifier: DocumentClassifierPort | None,
        extractor: StructuredExtractorPort | None,
        classify_enabled: bool,
        extract_enabled: bool,
        call_order: tuple[LlamaStop, ...],
        classify_max_pages: int,
        parse_configuration_hash: str,
        classification_configuration_hash: str,
        extraction_configuration_hash: str,
        event_logger: LlamaPhaseEventLogger | None = None,
    ) -> None:
        _validate_call_order(
            call_order,
            classify_enabled=classify_enabled,
            extract_enabled=extract_enabled,
        )
        self._parser = parser
        self._classifier = classifier
        self._extractor = extractor
        self._classify_enabled = classify_enabled
        self._extract_enabled = extract_enabled
        self._call_order = call_order
        self._classify_max_pages = classify_max_pages
        self._parse_configuration_hash = parse_configuration_hash
        self._classification_configuration_hash = classification_configuration_hash
        self._extraction_configuration_hash = extraction_configuration_hash
        self._event_logger = event_logger

    async def run(
        self,
        *,
        document_id: str,
        source_path: Path,
        source_hash: str,
        mime_type: str,
    ) -> LlamaPipelineResult:
        warnings: list[str] = []
        document_type = None
        topic = None
        schema_extract = None
        extraction = None
        parsed: ParsedDocument | None = None

        for stop in self._call_order:
            if stop == "classify":
                if self._classify_enabled and self._classifier is not None:
                    upstream_job_id = parsed.provider_job.job_id if parsed else None
                    self._log_phase_event(
                        level="info",
                        capability="classify",
                        event="llama_classify_start",
                        status="started",
                        message="LlamaClassify started",
                        document_id=document_id,
                        source_path=source_path,
                        upstream_job_id=upstream_job_id,
                        configuration_hash=self._classification_configuration_hash,
                    )
                    try:
                        document_type, topic = await self._run_classify(
                            document_id=document_id,
                            source_path=source_path,
                            parse_job_id=upstream_job_id,
                        )
                    except Exception as exc:
                        self._log_phase_event(
                            level="error",
                            capability="classify",
                            event="llama_classify_failed",
                            status="failed",
                            message="LlamaClassify failed",
                            document_id=document_id,
                            source_path=source_path,
                            upstream_job_id=upstream_job_id,
                            configuration_hash=self._classification_configuration_hash,
                            warning_code="llama_classify_failed",
                            exception=exc,
                        )
                        raise
                    self._log_phase_event(
                        level="info",
                        capability="classify",
                        event="llama_classify_finished",
                        status="completed",
                        message="LlamaClassify completed",
                        document_id=document_id,
                        source_path=source_path,
                        job_id=_classification_job_ids(document_type, topic),
                        upstream_job_id=upstream_job_id,
                        configuration_hash=self._classification_configuration_hash,
                        result_count=2,
                    )
                    schema_extract = extraction_schema_for_document_type(
                        document_type.selected.label
                    )
                else:
                    warnings.append("llama_classify_disabled")
                    self._log_phase_event(
                        level="warning",
                        capability="classify",
                        event="llama_classify_skipped",
                        status="skipped",
                        message="LlamaClassify skipped because it is disabled",
                        document_id=document_id,
                        source_path=source_path,
                        configuration_hash=self._classification_configuration_hash,
                        warning_code="llama_classify_disabled",
                    )
            elif stop == "parse":
                self._log_phase_event(
                    level="info",
                    capability="parse",
                    event="llama_parse_start",
                    status="started",
                    message="LlamaParse started",
                    document_id=document_id,
                    source_path=source_path,
                    configuration_hash=self._parse_configuration_hash,
                )
                try:
                    parsed = await self._parser.parse(
                        ParseRequest(
                            document_id=document_id,
                            source_path=source_path,
                            source_hash=source_hash,
                            mime_type=mime_type,
                            configuration_hash=self._parse_configuration_hash,
                        )
                    )
                except Exception as exc:
                    self._log_phase_event(
                        level="error",
                        capability="parse",
                        event="llama_parse_failed",
                        status="failed",
                        message="LlamaParse failed",
                        document_id=document_id,
                        source_path=source_path,
                        configuration_hash=self._parse_configuration_hash,
                        warning_code="llama_parse_failed",
                        exception=exc,
                    )
                    raise
                self._log_phase_event(
                    level="info",
                    capability="parse",
                    event="llama_parse_finished",
                    status="completed",
                    message="LlamaParse completed",
                    document_id=document_id,
                    source_path=source_path,
                    job_id=parsed.provider_job.job_id,
                    configuration_hash=self._parse_configuration_hash,
                    result_count=len(parsed.markdown_pages),
                )
            elif stop == "extract":
                if parsed is None:
                    raise ValueError("LlamaExtract requires parse to run first")
                if self._extract_enabled and self._extractor is not None:
                    schema_name = schema_extract or "document_control"
                    self._log_phase_event(
                        level="info",
                        capability="extract",
                        event="llama_extract_start",
                        status="started",
                        message="LlamaExtract started",
                        document_id=document_id,
                        source_path=source_path,
                        upstream_job_id=parsed.provider_job.job_id,
                        configuration_hash=self._extraction_configuration_hash,
                    )
                    try:
                        extraction = await self._extractor.extract(
                            ExtractionRequest(
                                document_id=document_id,
                                schema_name=schema_name,
                                parse_job_id=parsed.provider_job.job_id,
                                configuration_hash=self._extraction_configuration_hash,
                            )
                        )
                    except Exception as exc:
                        self._log_phase_event(
                            level="error",
                            capability="extract",
                            event="llama_extract_failed",
                            status="failed",
                            message="LlamaExtract failed",
                            document_id=document_id,
                            source_path=source_path,
                            upstream_job_id=parsed.provider_job.job_id,
                            configuration_hash=self._extraction_configuration_hash,
                            warning_code="llama_extract_failed",
                            exception=exc,
                        )
                        raise
                    warnings.extend(
                        _unsupported_critical_field_warnings(extraction, parsed)
                    )
                    self._log_phase_event(
                        level="info",
                        capability="extract",
                        event="llama_extract_finished",
                        status="completed",
                        message="LlamaExtract completed",
                        document_id=document_id,
                        source_path=source_path,
                        job_id=extraction.provider_job.job_id,
                        upstream_job_id=parsed.provider_job.job_id,
                        configuration_hash=self._extraction_configuration_hash,
                        result_count=len(extraction.fields),
                        warning_count=len(warnings),
                    )
                else:
                    warnings.append("llama_extract_disabled")
                    self._log_phase_event(
                        level="warning",
                        capability="extract",
                        event="llama_extract_skipped",
                        status="skipped",
                        message="LlamaExtract skipped because it is disabled",
                        document_id=document_id,
                        source_path=source_path,
                        upstream_job_id=parsed.provider_job.job_id,
                        configuration_hash=self._extraction_configuration_hash,
                        warning_code="llama_extract_disabled",
                    )

        if parsed is None:
            raise ValueError("Llama cloud lane requires parse")

        understanding = LlamaUnderstanding(
            parse_job_id=parsed.provider_job.job_id,
            document_type=document_type,
            topic=topic,
            schema_extract=schema_extract,
            extraction=extraction,
            warnings=list(dict.fromkeys(warnings)),
        )
        return LlamaPipelineResult(parsed=parsed, understanding=understanding)

    def _log_phase_event(
        self,
        *,
        level: LlamaLogLevel,
        capability: LlamaStop,
        event: str,
        status: str,
        message: str,
        document_id: str,
        source_path: Path,
        job_id: str | None = None,
        upstream_job_id: str | None = None,
        configuration_hash: str | None = None,
        result_count: int | None = None,
        warning_count: int | None = None,
        warning_code: str | None = None,
        exception: BaseException | None = None,
    ) -> None:
        log_extra = {
            "document_id": document_id,
            "source_path": str(source_path),
            "stage": "llama_cloud",
            "event": event,
            "status": status,
            "provider": "llama_cloud",
            "capability": capability,
            "job_id": job_id,
            "upstream_job_id": upstream_job_id,
            "configuration_hash": configuration_hash,
            "result_count": result_count,
            "warning_count": warning_count,
            "warning_code": warning_code,
        }
        phase_logger.log(
            _python_log_level(level),
            message,
            extra=log_extra,
            exc_info=(
                (type(exception), exception, exception.__traceback__)
                if exception
                else None
            ),
        )
        if self._event_logger is None:
            return
        self._event_logger.event(
            stage="llama_cloud",
            event=event,
            status=status,
            message=message,
            level=level,
            document_id=document_id,
            source_path=str(source_path),
            provider="llama_cloud",
            capability=capability,
            job_id=job_id,
            upstream_job_id=upstream_job_id,
            configuration_hash=configuration_hash,
            result_count=result_count,
            warning_count=warning_count,
            warning_code=warning_code,
            exception=exception,
        )

    async def _run_classify(
        self,
        *,
        document_id: str,
        source_path: Path,
        parse_job_id: str | None,
    ):
        if self._classifier is None:
            raise ValueError("LlamaClassify is enabled but no classifier was provided")
        document_type = await self._classifier.classify(
            ClassificationRequest(
                document_id=document_id,
                source_path=source_path,
                parse_job_id=parse_job_id,
                labels=tuple(classification_labels()),
                label_descriptions=classification_labels(),
                max_pages=self._classify_max_pages,
                configuration_hash=self._classification_configuration_hash,
            )
        )
        topic = await self._classifier.classify(
            ClassificationRequest(
                document_id=document_id,
                source_path=source_path,
                parse_job_id=parse_job_id,
                labels=tuple(topic_classification_labels()),
                label_descriptions=topic_classification_labels(),
                max_pages=self._classify_max_pages,
                configuration_hash=self._classification_configuration_hash,
            )
        )
        return document_type, topic


def _unsupported_critical_field_warnings(
    extraction: ExtractionResult,
    parsed: ParsedDocument,
) -> list[str]:
    text = _normalize_text("\n".join(page.markdown for page in parsed.markdown_pages))
    warnings: list[str] = []
    for field in extraction.fields:
        if field.critical and not _field_value_supported(field, text):
            warnings.append(f"llama_extract_unsupported_critical_field:{field.name}")
    return warnings


def _field_value_supported(field: ExtractionField, normalized_text: str) -> bool:
    if field.value is None:
        return True
    value = _normalize_text(str(field.value))
    if not value:
        return True
    if value in normalized_text:
        return True
    return any(
        evidence.text and _normalize_text(evidence.text) in normalized_text
        for evidence in field.evidence
    )


def _classification_job_ids(*results: ClassificationResult | None) -> str:
    return ",".join(result.provider_job.job_id for result in results if result is not None)


def _python_log_level(level: LlamaLogLevel) -> int:
    if level == "error":
        return logging.ERROR
    if level == "warning":
        return logging.WARNING
    return logging.INFO


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_accents.replace("_", " ").replace("-", " ").split())


def _validate_call_order(
    call_order: tuple[LlamaStop, ...],
    *,
    classify_enabled: bool,
    extract_enabled: bool,
) -> None:
    if not call_order:
        raise ValueError("Llama call order must not be empty")
    if call_order.count("parse") != 1:
        raise ValueError("Llama call order must include exactly one parse stop")
    if len(set(call_order)) != len(call_order):
        raise ValueError("Llama call order cannot repeat stops")
    if "extract" in call_order and call_order.index("extract") < call_order.index("parse"):
        raise ValueError("LlamaExtract must run after LlamaParse")
    if (
        classify_enabled
        and extract_enabled
        and "classify" in call_order
        and "extract" in call_order
        and call_order.index("classify") > call_order.index("extract")
    ):
        raise ValueError("LlamaClassify must run before LlamaExtract when both stops are enabled")
