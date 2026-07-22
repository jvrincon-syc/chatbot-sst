from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Literal

from ingestion.application.ports.classifier import DocumentClassifierPort
from ingestion.application.ports.classifier import ClassificationRequest
from ingestion.application.ports.extractor import ExtractionRequest
from ingestion.application.ports.extractor import StructuredExtractorPort
from ingestion.application.ports.parser import DocumentParserPort, ParseRequest
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.llama_understanding import LlamaPipelineResult, LlamaUnderstanding
from ingestion.domain.models.parsed_document import ParsedDocument
from ingestion.infrastructure.llama_cloud.classify_rules import (
    classification_labels,
    extraction_schema_for_document_type,
    topic_classification_labels,
)

LlamaStop = Literal["classify", "parse", "extract"]


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
                    document_type, topic = await self._run_classify(
                        document_id=document_id,
                        source_path=source_path,
                        parse_job_id=parsed.provider_job.job_id if parsed else None,
                    )
                    schema_extract = extraction_schema_for_document_type(
                        document_type.selected.label
                    )
                else:
                    warnings.append("llama_classify_disabled")
            elif stop == "parse":
                parsed = await self._parser.parse(
                    ParseRequest(
                        document_id=document_id,
                        source_path=source_path,
                        source_hash=source_hash,
                        mime_type=mime_type,
                        configuration_hash=self._parse_configuration_hash,
                    )
                )
            elif stop == "extract":
                if parsed is None:
                    raise ValueError("LlamaExtract requires parse to run first")
                if self._extract_enabled and self._extractor is not None:
                    extraction = await self._extractor.extract(
                        ExtractionRequest(
                            document_id=document_id,
                            schema_name=schema_extract or "document_control",
                            parse_job_id=parsed.provider_job.job_id,
                            configuration_hash=self._extraction_configuration_hash,
                        )
                    )
                    warnings.extend(
                        _unsupported_critical_field_warnings(extraction, parsed)
                    )
                else:
                    warnings.append("llama_extract_disabled")

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
