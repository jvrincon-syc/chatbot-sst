from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional
from time import perf_counter

from pydantic import ValidationError

from core.logging.observability import measure_duration_ms
from ingestion.application.platform_metadata import (
    PlatformMetadataContext,
    apply_platform_metadata,
)
from ingestion.classification.rules import classify_document
from ingestion.document_control.extractor import extract_document_control
from ingestion.inventory.scanner import scan_docs_raw
from ingestion.logging.jsonl import JsonlLogger
from ingestion.manifests.bundle_writer import BundlePayload, write_bundle_atomic
from ingestion.manifests.writer import dump_json, write_inventory
from ingestion.fingerprint import processing_fingerprint
from ingestion.application.services.llama_orchestrator import LlamaOrchestrator
from ingestion.config.llama_settings import LlamaSettings, load_llama_settings
from ingestion.infrastructure.llama_cloud.classify_adapter import LlamaClassifyAdapter
from ingestion.infrastructure.llama_cloud.classify_config import LlamaClassifyConfig
from ingestion.infrastructure.llama_cloud.classify_rules import (
    canonical_topic,
    classification_labels,
)
from ingestion.infrastructure.llama_cloud.extract_adapter import LlamaExtractAdapter
from ingestion.infrastructure.llama_cloud.extract_config import LlamaExtractConfig
from ingestion.infrastructure.llama_cloud.parse_adapter import LlamaParseAdapter
from ingestion.infrastructure.llama_cloud.parse_config import LlamaParseConfig
from ingestion.paths import ArtifactPaths, canonical_relpath
from ingestion.promotion import PromotionError, promote_candidate
from ingestion.readers.base import ReadResult
from ingestion.ocr.ocrmypdf_engine import OcrDependencyError, OcrMyPdfEngine
from ingestion.ocr.tesseract_engine import TesseractEngine, TesseractPdfEngine
from ingestion.readers.markdown_reader import MarkdownReader
from ingestion.readers.hybrid_reader import HybridReader
from ingestion.readers.llama_parse_reader import LlamaParseReader
from ingestion.readers.pdf_digital_reader import PdfDigitalReader
from ingestion.readers.pdf_scanned_reader import PdfScannedReader
from ingestion.schemas.artifacts import (
    Classification,
    DocumentControl,
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.common import ConfidenceMetric, DocumentField, Evidence, Observation
from ingestion.domain.models.llama_understanding import LlamaUnderstanding
from ingestion.schemas.inventory import InventoryRecord
from ingestion.schemas.manifests import ErrorManifest, ErrorItem, ReviewManifest, ReviewItem, RunDocument, RunManifest
from ingestion.structure.handwriting import HandwritingDetector
from ingestion.validation.normalized import validate_normalized_tree

_MATERIAL_PAGE_WARNINGS = {
    "incomplete_coverage",
    "insufficient_coverage",
    "partial_extraction",
    "uncovered_substantive_region",
    "ocr_unavailable_for_substantive_gap",
    "table_detected_not_reconstructed",
    "form_detected_not_reconstructed",
}
DEFAULT_OCR_REVIEW_THRESHOLD = 0.80
_LLAMA_PARSE_METHODS = {"llamaparse", "hybrid_llamaparse"}
console_logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _relative_output_base(source_path: Path, docs_raw: Path, docs_normalized: Path) -> Path:
    relative = source_path.relative_to(docs_raw)
    return docs_normalized / relative.with_suffix("")


def _output_base_for_record(record: InventoryRecord, docs_normalized: Path) -> Path:
    return docs_normalized / Path(record.source_relpath).with_suffix("")


def _metadata_path_for_record(record: InventoryRecord, docs_raw: Path, docs_normalized: Path) -> Path:
    return _output_base_for_record(record, docs_normalized).with_suffix(".metadata.json")


def _markdown_path_for_record(record: InventoryRecord, docs_raw: Path, docs_normalized: Path) -> Path:
    return _output_base_for_record(record, docs_normalized).with_suffix(".md")


def _load_previous_inventory(path: Path) -> Dict[str, InventoryRecord]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload = payload["records"]
    if not isinstance(payload, list):
        return {}
    records: Dict[str, InventoryRecord] = {}
    for item in payload:
        try:
            record = InventoryRecord(**item)
        except (TypeError, ValidationError):
            continue
        records[record.source_relpath] = record
    return records


def _can_skip_record(
    record: InventoryRecord,
    previous_records: Dict[str, InventoryRecord],
    docs_raw: Path,
    docs_normalized: Path,
) -> bool:
    previous = previous_records.get(record.source_relpath)
    if previous is None:
        return False
    if previous.document_id != record.document_id:
        return False
    if previous.content_hash != record.content_hash:
        return False
    if previous.processing_status not in {"processed", "needs_review"}:
        return False
    return (
        _markdown_path_for_record(record, docs_raw, docs_normalized).exists()
        and _metadata_path_for_record(record, docs_raw, docs_normalized).exists()
    )


def _front_matter(metadata: MetadataArtifact) -> str:
    fields = {
        "document_id": metadata.document_id,
        "document_type": metadata.classification.document_type,
        "topic": metadata.classification.topic,
        "source_relpath": metadata.source_relpath,
        "extraction_method": metadata.extraction_method,
        "page_count": metadata.page_count,
        "corpus_version": metadata.corpus_version,
        "pipeline_version": metadata.pipeline_version,
    }
    lines = ["---"]
    for key, value in fields.items():
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _set_artifact_document_id(result: ReadResult, document_id: str) -> None:
    if result.ocr is not None:
        result.ocr.document_id = document_id
    if result.tables is not None:
        result.tables.document_id = document_id
        for index, table in enumerate(result.tables.tables, start=1):
            if table.table_id == "pending":
                table.table_id = f"{document_id}_table_{index:03d}"
    if result.forms is not None:
        result.forms.document_id = document_id


def _build_metadata(
    *,
    record: InventoryRecord,
    normalized_md: Path,
    result: ReadResult,
    source_path: Path,
    corpus_version: str,
    pipeline_version: str,
    classification_review_threshold: float,
    ocr_review_threshold: float,
) -> MetadataArtifact:
    document_control = _reconcile_llama_document_control(
        extract_document_control(result.pages, record.document_name),
        result.llama_understanding,
    )
    classification = _reconcile_llama_classification(
        classify_document(record.source_relpath, result.pages, document_control),
        result.llama_understanding,
    )
    ocr_confidence = _document_ocr_confidence_from_result(result)
    handwriting = _handwriting_observation(result, record=record, source_path=source_path)
    tables = (
        Observation(
            status="detected",
            value=True,
            method="reader_tables",
            evidence=[Evidence(source="tables_artifact")],
            warnings=["table_evidence_available_in_tables_artifact"],
        )
        if result.tables is not None and result.tables.table_count > 0
        else _artifact_observation(
            result.tables.page_observations if result.tables is not None else []
        )
    )
    forms = (
        Observation(
            status="detected",
            value=True,
            method="reader_forms",
            evidence=[Evidence(source="forms_artifact")],
            warnings=["form_evidence_available_in_forms_artifact"],
        )
        if result.forms is not None and result.forms.groups
        else _artifact_observation(
            result.forms.page_observations if result.forms is not None else []
        )
    )
    page_warnings = [
        warning
        for page in result.pages
        for warning in page.warnings
    ]
    ocr_review_reasons = _ocr_confidence_review_reasons(
        record=record,
        result=result,
        ocr_confidence=ocr_confidence,
        ocr_review_threshold=ocr_review_threshold,
    )
    warnings = _unique(
        list(result.warnings)
        + page_warnings
        + ocr_review_reasons
        + document_control.warnings
        + classification.warnings
        + classification.conflicts
    )
    review_reasons = _unique(
        list(result.review_reasons)
        + ocr_review_reasons
        + [
            warning
            for warning in page_warnings
            if warning in _MATERIAL_PAGE_WARNINGS
        ]
        + document_control.warnings
        + _llama_extract_review_reasons(result.llama_understanding)
        + (["classification_conflict"] if classification.conflicts else [])
        + _material_feature_review_reasons(
            record=record,
            handwriting=handwriting,
            tables=tables,
            forms=forms,
        )
    )
    if (classification.document_type_confidence.value or 0) < classification_review_threshold:
        warnings.append("ambiguous_classification")
        review_reasons.append("ambiguous_classification")
    result.review_reasons = _unique(review_reasons)
    result.warnings = _unique(warnings)
    return MetadataArtifact(
        schema_version="2.0",
        document_id=record.document_id,
        document_name=record.document_name,
        source_relpath=record.source_relpath,
        normalized_relpath=Path(record.source_relpath).with_suffix(".md").as_posix(),
        legacy_normalized_path=str(normalized_md),
        document_control=document_control,
        classification=classification,
        page_count=result.page_count,
        extraction_method=result.extraction_method,
        ocr_confidence=ocr_confidence,
        handwriting=handwriting,
        tables=tables,
        forms=forms,
        llama_cloud=result.llama_cloud_metadata,
        source_hash=record.content_hash,
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        processing_status="needs_review" if result.review_reasons else "processed",
        review_reasons=result.review_reasons,
        warnings=result.warnings,
        processed_at=_now(),
    )


_LLAMA_SUPPORTED_DOCUMENT_TYPES = {
    "manual",
    "formulario",
    "politica",
    "reglamento",
    "programa",
    "matriz",
    "procedimiento",
    "anexo",
    "instructivo",
    "capacitacion",
    "acta",
    "norma",
    "guia",
    "informacion_general",
    "otro",
}
_LLAMA_DOCUMENT_CONTROL_FIELDS = {
    "title",
    "code",
    "version",
    "publication_date",
    "effective_date",
}
_LLAMA_EXTRACT_UNSUPPORTED_PREFIX = "llama_extract_unsupported_critical_field:"


def _reconcile_llama_classification(
    local: Classification,
    understanding: LlamaUnderstanding | None,
) -> Classification:
    if understanding is None:
        return local
    updates = {}
    warnings = list(local.warnings)
    signals = list(local.signals)
    conflicts = list(local.conflicts)

    if understanding.document_type is not None:
        label = understanding.document_type.selected.label
        if label in _LLAMA_SUPPORTED_DOCUMENT_TYPES:
            updates["document_type"] = label
            updates["document_type_confidence"] = ConfidenceMetric(
                kind="estimated",
                value=understanding.document_type.selected.confidence,
                method="llama_classify",
                provenance=understanding.document_type.provider_job.job_id,
            )
            signals.append(f"llama_classify_document_type:{label}")
            conflicts = [
                conflict
                for conflict in conflicts
                if "type_route" not in conflict and "type_title_control" not in conflict
            ]
        else:
            warnings.append(f"llama_classify_unknown_document_type:{label}")

    if understanding.topic is not None:
        label = understanding.topic.selected.label
        topic = canonical_topic(label)
        updates["topic"] = topic
        updates["topic_confidence"] = ConfidenceMetric(
            kind="estimated",
            value=understanding.topic.selected.confidence,
            method="llama_classify",
            provenance=understanding.topic.provider_job.job_id,
        )
        signals.append(f"llama_classify_topic:{label}")
        conflicts = [
            conflict
            for conflict in conflicts
            if "topic_route" not in conflict and "topic_title_control" not in conflict
        ]

    if understanding.schema_extract:
        signals.append(f"llama_schema_extract:{understanding.schema_extract}")
    warnings.extend(understanding.warnings)
    updates["signals"] = _unique(signals)
    updates["warnings"] = _unique(warnings)
    updates["conflicts"] = _unique(conflicts)
    updates["conflict_status"] = "conflicting" if conflicts else "none"
    return local.model_copy(update=updates)


def _reconcile_llama_document_control(
    local: DocumentControl,
    understanding: LlamaUnderstanding | None,
) -> DocumentControl:
    if understanding is None or understanding.extraction is None:
        return local
    unsupported_fields = {
        warning.removeprefix(_LLAMA_EXTRACT_UNSUPPORTED_PREFIX)
        for warning in understanding.warnings
        if warning.startswith(_LLAMA_EXTRACT_UNSUPPORTED_PREFIX)
    }
    updates = {}
    for field in understanding.extraction.fields:
        if field.name not in _LLAMA_DOCUMENT_CONTROL_FIELDS:
            continue
        if field.name in unsupported_fields:
            continue
        if field.value is None or not field.evidence:
            continue
        updates[field.name] = DocumentField(
            value=field.value,
            value_raw=field.value,
            status="extracted",
            evidence=field.evidence,
            warnings=_unique([*field.warnings, "llama_extract_field"]),
        )
    if not updates:
        return local
    return local.model_copy(update=updates)


def _llama_extract_review_reasons(understanding: LlamaUnderstanding | None) -> list[str]:
    if understanding is None:
        return []
    return [
        warning
        for warning in understanding.warnings
        if warning.startswith(_LLAMA_EXTRACT_UNSUPPORTED_PREFIX)
    ]


def _ocr_confidence_review_reasons(
    *,
    record: InventoryRecord,
    result: ReadResult,
    ocr_confidence: ConfidenceMetric,
    ocr_review_threshold: float,
) -> list[str]:
    if record.detected_extension != ".pdf":
        return []
    if ocr_confidence.value is None:
        if result.extraction_method in _LLAMA_PARSE_METHODS:
            return ["ocr_confidence_unavailable"]
        return []
    if ocr_confidence.value < ocr_review_threshold:
        return ["low_ocr_confidence"]
    return []


def _document_ocr_confidence_from_result(result: ReadResult) -> ConfidenceMetric:
    if result.ocr is not None:
        return result.ocr.document_confidence
    page_metrics = [page.ocr_confidence for page in result.pages]
    values = [
        metric.value
        for metric in page_metrics
        if metric.value is not None
    ]
    if not values:
        return ConfidenceMetric(kind="unavailable", value=None)
    return ConfidenceMetric(
        kind="estimated",
        value=sum(values) / len(values),
        method="page_ocr_confidence_average",
    )


def _write_success_artifacts(
    *,
    record: InventoryRecord,
    result: ReadResult,
    docs_raw: Path,
    docs_normalized: Path,
    corpus_version: str,
    pipeline_version: str,
    classification_review_threshold: float,
    ocr_review_threshold: float,
    platform_context: PlatformMetadataContext | None = None,
) -> tuple[MetadataArtifact, object]:
    paths = ArtifactPaths.for_source(record.source_relpath)
    normalized_md = docs_normalized / Path(paths.markdown)

    _set_artifact_document_id(result, record.document_id)
    metadata = _build_metadata(
        record=record,
        normalized_md=normalized_md,
        result=result,
        source_path=_source_path_for_record(record, docs_raw),
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        classification_review_threshold=classification_review_threshold,
        ocr_review_threshold=ocr_review_threshold,
    )
    # Aditivo: solo la vía de plataforma adjunta identidad y provenance. Sin
    # contexto, el metadata queda idéntico al legacy.
    if platform_context is not None:
        metadata = apply_platform_metadata(metadata, platform_context)
    pages = PagesArtifact(schema_version="2.0", document_id=record.document_id, page_count=result.page_count, pages=result.pages)
    ocr = result.ocr or OcrArtifact(
        schema_version="2.0",
        document_id=record.document_id,
        document_confidence=ConfidenceMetric(kind="unavailable", value=None),
        pages=[],
        warnings=["ocr_not_evaluated"],
    )
    tables = result.tables or TablesArtifact(
        schema_version="2.0",
        document_id=record.document_id,
        table_count=0,
        tables=[],
        page_observations=[
            Observation(status="not_evaluated", value=None)
            for _page in result.pages
        ],
        warnings=["table_detection_not_evaluated"],
    )
    forms = result.forms or FormsArtifact(
        schema_version="2.0",
        document_id=record.document_id,
        groups=[],
        page_observations=[
            Observation(status="not_evaluated", value=None)
            for _page in result.pages
        ],
        warnings=["form_detection_not_evaluated"],
    )
    artifacts = {
        paths.markdown: _front_matter(metadata) + result.markdown + "\n",
        paths.metadata: metadata,
        paths.pages: pages,
        paths.ocr: ocr,
        paths.tables: tables,
        paths.forms: forms,
    }
    fingerprint = processing_fingerprint(
        {
            "pipeline_version": pipeline_version,
            "corpus_version": corpus_version,
            "classification_review_threshold": classification_review_threshold,
            "ocr_review_threshold": ocr_review_threshold,
        },
        {},
    )
    bundle = write_bundle_atomic(
        docs_normalized,
        BundlePayload(
            document_id=record.document_id,
            source_relpath=record.source_relpath,
            source_hash=record.content_hash,
            processing_fingerprint=fingerprint,
            document_status=metadata.processing_status,
            artifacts=artifacts,
        ),
    )
    return metadata, bundle


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _handwriting_observation(
    result: ReadResult,
    *,
    record: InventoryRecord,
    source_path: Path,
) -> Observation:
    if result.ocr is None or not result.ocr.pages:
        if record.detected_extension == ".pdf":
            return HandwritingDetector().evaluate_pdf(
                source_path,
                page_texts=_page_texts_by_number(result),
            )
        return Observation(status="not_evaluated", value=None)
    for page in result.ocr.pages:
        if page.handwriting.status == "detected":
            return page.handwriting
    detected = HandwritingDetector().evaluate_pdf(
        source_path,
        page_texts=_page_texts_by_number(result),
    )
    if detected.status == "detected":
        return detected
    if all(page.handwriting.status == "not_detected" for page in result.ocr.pages):
        return result.ocr.pages[0].handwriting
    return detected


def _page_texts_by_number(result: ReadResult) -> dict[int, str]:
    return {
        page.page_number: page.text_normalized or page.text_raw
        for page in result.pages
    }


def _material_feature_review_reasons(
    *,
    record: InventoryRecord,
    handwriting: Observation,
    tables: Observation,
    forms: Observation,
) -> list[str]:
    if record.detected_extension != ".pdf":
        return []
    reasons = []
    for name, observation in (
        ("handwriting", handwriting),
        ("tables", tables),
        ("forms", forms),
    ):
        if observation.status == "not_evaluated":
            reasons.append(f"{name}_not_evaluated")
    if reasons:
        reasons.insert(0, "pdf_semantic_review_required")
    return reasons


def _artifact_observation(observations: list[Observation]) -> Observation:
    if not observations:
        return Observation(status="not_evaluated", value=None)
    detected = next(
        (observation for observation in observations if observation.status == "detected"),
        None,
    )
    if detected is not None:
        return detected
    if all(observation.status == "not_detected" for observation in observations):
        return observations[0]
    return Observation(status="not_evaluated", value=None)


def _source_path_for_record(record: InventoryRecord, docs_raw: Optional[Path] = None) -> Path:
    if docs_raw is not None:
        return docs_raw / record.source_relpath
    if record.legacy_path:
        return Path(record.legacy_path)
    return Path(record.source_relpath)


def _configured_tesseract_engine() -> TesseractEngine:
    return TesseractEngine(
        tesseract_cmd=os.getenv("TESSERACT_CMD", "tesseract"),
        language=os.getenv("TESSERACT_LANGUAGE", "spa"),
        engine_version=os.getenv("TESSERACT_VERSION", "unknown"),
        low_confidence_threshold=float(
            os.getenv("OCR_LOW_CONFIDENCE_THRESHOLD", "0.70")
        ),
    )


def _configured_tesseract_pdf_engine() -> TesseractPdfEngine:
    return TesseractPdfEngine(region_engine=_configured_tesseract_engine())


def _choose_pdf_reader(
    *,
    llama_cloud_enabled: bool,
    local_fallback_enabled: bool,
    local_reader_factory,
    llama_reader_factory=None,
):
    if llama_cloud_enabled and llama_reader_factory is not None:
        return llama_reader_factory()
    if local_fallback_enabled:
        return local_reader_factory()
    if llama_reader_factory is None:
        raise RuntimeError("Llama Cloud PDF reader is not configured and local fallback is disabled")
    return llama_reader_factory()


def _configured_llama_parse_reader(
    settings=None,
    event_logger: JsonlLogger | None = None,
) -> LlamaParseReader:
    from ingestion.infrastructure.llama_cloud.client_factory import (
        create_async_llama_cloud_client,
    )

    settings = settings or load_llama_settings()
    parse_config = LlamaParseConfig.from_settings(settings)
    client = create_async_llama_cloud_client(settings)
    parse_adapter = LlamaParseAdapter(client=client, config=parse_config)
    classify_config = LlamaClassifyConfig(
        mode=settings.classify_mode,
        language=settings.parse_ocr_languages[0] if settings.parse_ocr_languages else "es",
        max_pages=settings.classify_max_pages,
    )
    extract_config = LlamaExtractConfig(
        schema_name="document_control",
        critical_fields=(
            "title",
            "code",
            "version",
            "publication_date",
            "effective_date",
        ),
        data_schema=_llama_extract_document_control_schema(),
        tier=settings.extract_tier,
        parse_tier=settings.extract_parse_tier,
        version=settings.parse_version,
        max_pages=settings.extract_max_pages,
    )
    orchestrator = LlamaOrchestrator(
        parser=parse_adapter,
        classifier=LlamaClassifyAdapter(client=client, config=classify_config),
        extractor=LlamaExtractAdapter(client=client, config=extract_config),
        classify_enabled=settings.classify_enabled,
        extract_enabled=settings.extract_enabled,
        call_order=settings.call_order,
        classify_max_pages=settings.classify_max_pages,
        parse_configuration_hash=parse_config.configuration_hash(),
        classification_configuration_hash=classify_config.configuration_hash(
            labels=tuple(classification_labels())
        ),
        extraction_configuration_hash=extract_config.configuration_hash(),
        event_logger=event_logger,
    )
    return LlamaParseReader(
        adapter=parse_adapter,
        configuration_hash=parse_config.configuration_hash(),
        orchestrator=orchestrator,
        async_client=client,
    )


def _llama_extract_document_control_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "code": {"type": "string"},
            "version": {"type": "string"},
            "publication_date": {"type": "string"},
            "effective_date": {"type": "string"},
            "responsible": {"type": "string"},
            "obligations": {"type": "array", "items": {"type": "string"}},
            "table_summaries": {"type": "array", "items": {"type": "string"}},
            "form_fields": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def _configured_local_pdf_reader(ocr_engine=None):
    region_ocr = (
        ocr_engine
        if ocr_engine is not None and hasattr(ocr_engine, "recognize")
        else _configured_tesseract_engine()
    )
    return HybridReader(
        digital_reader=PdfDigitalReader(),
        ocr_engine=region_ocr,
    )


def _read_document(
    record: InventoryRecord,
    pdf_reader_factory=None,
    ocr_engine=None,
    docs_raw: Optional[Path] = None,
    llama_settings: LlamaSettings | None = None,
    event_logger: JsonlLogger | None = None,
) -> ReadResult:
    started_at = perf_counter()
    source_path = _source_path_for_record(record, docs_raw)
    if record.detected_extension == ".md":
        return MarkdownReader().read(source_path)
    if record.detected_extension == ".pdf":
        if pdf_reader_factory:
            pdf_reader_or_extractor = pdf_reader_factory()
            pdf_reader = (
                pdf_reader_or_extractor
                if hasattr(pdf_reader_or_extractor, "read")
                else PdfDigitalReader(extractor=pdf_reader_or_extractor)
            )
        else:
            settings = llama_settings or load_llama_settings()
            pdf_reader = _choose_pdf_reader(
                llama_cloud_enabled=settings.cloud_enabled,
                local_fallback_enabled=settings.local_fallback_enabled,
                local_reader_factory=lambda: _configured_local_pdf_reader(ocr_engine),
                llama_reader_factory=(
                    lambda: _configured_llama_parse_reader(settings, event_logger)
                )
                if settings.cloud_enabled
                else None,
            )
        try:
            if isinstance(pdf_reader, LlamaParseReader):
                return pdf_reader.read(
                    source_path,
                    document_id=record.document_id,
                    source_hash=record.content_hash,
                )
            return pdf_reader.read(source_path)
        except RuntimeError as exc:
            fallback_signals = (
                "No PDF extractor configured",
                "PDF text layer insufficient",
                "PDF text extraction failed",
            )
            if not any(signal in str(exc) for signal in fallback_signals):
                raise
            fallback_engine = ocr_engine or _configured_tesseract_pdf_engine()
            return PdfScannedReader(ocr_engine=fallback_engine).read(source_path)
        except Exception as exc:
            settings = llama_settings or load_llama_settings()
            if settings.cloud_enabled and settings.local_fallback_enabled:
                result = _configured_local_pdf_reader(ocr_engine).read(source_path)
                result.warnings.append(f"cloud_fallback_used:{type(exc).__name__}")
                result.review_reasons.append("cloud_fallback_used")
                if event_logger is not None:
                    event_logger.event(
                        stage="reading",
                        event="document_fallback_activated",
                        status="warning",
                        message="Cloud fallback activated",
                        document_id=record.document_id,
                        source_path=record.source_relpath,
                        provider="llama_cloud",
                        capability="parse",
                        warning_code="cloud_fallback_used",
                        duration_ms=measure_duration_ms(started_at),
                        context={
                            "primary_provider": "llama_cloud",
                            "effective_provider": "local",
                            "fallback_reason": type(exc).__name__,
                        },
                        attributes={
                            "fallback_strategy": "local_fallback",
                        },
                    )
                return result
            raise
    raise ValueError(f"Unsupported format: {record.detected_extension or 'unknown'}")


def _is_cloud_pdf_failure(
    record: InventoryRecord,
    llama_settings_override: LlamaSettings | None,
) -> bool:
    if record.detected_extension != ".pdf":
        return False
    settings = llama_settings_override
    if settings is None:
        try:
            settings = load_llama_settings()
        except ValueError:
            return False
    return settings.cloud_enabled


def _failure_recommendation(reason: str, exc: Exception) -> str:
    if reason == "llama_cloud_provider_error":
        return "Revisar error de proveedor Llama Cloud en el log antes de reintentar."
    if isinstance(exc, OcrDependencyError):
        return "Instalar/configurar OCRmyPDF y el idioma spa de Tesseract."
    return "Configurar extractor PDF/OCR para este documento."


def _run_document(
    record: InventoryRecord,
    *,
    document_status: str,
    disposition: str,
    warnings: list[str] | None = None,
) -> RunDocument:
    return RunDocument(
        schema_version="2.0",
        document_id=record.document_id,
        source_relpath=record.source_relpath,
        document_status=document_status,
        disposition=disposition,
        warnings=warnings or [],
    )


def _run_pipeline_legacy(
    *,
    docs_raw: Path,
    docs_normalized: Path,
    staging_root: Optional[Path] = None,
    promote: bool = False,
    only_sources: Optional[List[str]] = None,
    force: bool = False,
    corpus_version: str = "1",
    pipeline_version: str = "1.0.0",
    run_id: Optional[str] = None,
    classification_review_threshold: float = 0.60,
    ocr_review_threshold: float = DEFAULT_OCR_REVIEW_THRESHOLD,
    golden_status: Optional[str] = None,
    llama_settings_override: LlamaSettings | None = None,
    request_id: str | None = None,
) -> Dict[str, int]:
    return run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=docs_normalized,
        staging_root=staging_root,
        promote=promote,
        only_sources=only_sources,
        force=force,
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        run_id=run_id,
        classification_review_threshold=classification_review_threshold,
        ocr_review_threshold=ocr_review_threshold,
        golden_status=golden_status,
        llama_settings_override=llama_settings_override,
        request_id=request_id,
    )


def run_pipeline(
    *,
    docs_raw: Path,
    docs_normalized: Path,
    staging_root: Optional[Path] = None,
    promote: bool = False,
    only_sources: Optional[List[str]] = None,
    force: bool = False,
    corpus_version: str = "1",
    pipeline_version: str = "1.0.0",
    run_id: Optional[str] = None,
    classification_review_threshold: float = 0.60,
    ocr_review_threshold: float = DEFAULT_OCR_REVIEW_THRESHOLD,
    golden_status: Optional[str] = None,
    llama_settings_override: LlamaSettings | None = None,
    request_id: str | None = None,
    platform_context_resolver: Callable[
        [InventoryRecord], PlatformMetadataContext | None
    ]
    | None = None,
) -> Dict[str, int]:
    run_id = run_id or "run_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    output_root = staging_root or docs_normalized
    manifests_dir = output_root / "_manifests"
    event_logger = JsonlLogger(
        manifests_dir / f"{run_id}_details.log",
        run_id,
        request_id=request_id,
    )
    started_at = perf_counter()
    summary = {"processed": 0, "failed": 0, "needs_review": 0, "skipped": 0}
    errors: List[dict] = []
    needs_review: List[dict] = []
    run_documents: List[dict] = []
    bundle_manifests: list[object] = []

    def _emit_pipeline_event(
        *,
        level: int,
        stage: str,
        event: str,
        status: str,
        message: str,
        document_id: str | None = None,
        source_path: str | None = None,
        warning_code: str | None = None,
        duration_ms: int | None = None,
        metrics: dict[str, int | float] | None = None,
        attributes: dict[str, object] | None = None,
        exception: BaseException | None = None,
    ) -> None:
        context: dict[str, object] = {"run_id": run_id}
        if request_id is not None:
            context["request_id"] = request_id
        if document_id is not None:
            context["document_id"] = document_id
        exc_info = (
            (type(exception), exception, exception.__traceback__)
            if exception is not None
            else None
        )
        payload_extra: dict[str, object] = {
            "run_id": run_id,
            "stage": stage,
            "event": event,
            "status": status,
            "event_message": message,
            "context": context,
            "metrics": metrics or {},
            "attributes": attributes or {},
        }
        if request_id is not None:
            payload_extra["request_id"] = request_id
        if document_id is not None:
            payload_extra["document_id"] = document_id
        if source_path is not None:
            payload_extra["source_path"] = source_path
        if warning_code is not None:
            payload_extra["warning_code"] = warning_code
        if duration_ms is not None:
            payload_extra["duration_ms"] = duration_ms
        console_logger.log(level, message, extra=payload_extra, exc_info=exc_info)
        event_logger.event(
            stage=stage,
            event=event,
            status=status,
            message=message,
            request_id=request_id,
            document_id=document_id,
            source_path=source_path,
            warning_code=warning_code,
            duration_ms=duration_ms,
            context=context,
            metrics=metrics,
            attributes=attributes,
            exception=exception,
        )

    _emit_pipeline_event(
        level=logging.INFO,
        stage="pipeline",
        event="pipeline_run_started",
        status="started",
        message="Pipeline run started",
        metrics={
            "classification_review_threshold": classification_review_threshold,
            "ocr_review_threshold": ocr_review_threshold,
        },
        attributes={
            "corpus_version": corpus_version,
            "pipeline_version": pipeline_version,
            "promote": promote,
        },
    )

    try:
        previous_records = _load_previous_inventory(manifests_dir / "inventory.json")
        records = scan_docs_raw(
            docs_raw,
            corpus_version=corpus_version,
            pipeline_version=pipeline_version,
        )
        if only_sources is not None:
            selected = {
                canonical_relpath(str(source).replace("\\", "/"))
                for source in only_sources
            }
            records = [record for record in records if record.source_relpath in selected]

        _emit_pipeline_event(
            level=logging.INFO,
            stage="inventory",
            event="pipeline_inventory_completed",
            status="completed",
            message="Inventory scan completed",
            metrics={"document_count": len(records)},
        )

        for record in records:
            document_started_at = perf_counter()
            _emit_pipeline_event(
                level=logging.INFO,
                stage="inventory",
                event="document_selected",
                status="started",
                message="Processing document",
                document_id=record.document_id,
                source_path=record.source_relpath,
            )
            if not force and _can_skip_record(record, previous_records, docs_raw, output_root):
                previous = previous_records[record.source_relpath]
                record.processing_status = previous.processing_status
                summary["skipped"] += 1
                run_documents.append(
                    _run_document(
                        record,
                        document_status=record.processing_status,
                        disposition="reused",
                    )
                )
                _emit_pipeline_event(
                    level=logging.INFO,
                    stage="inventory",
                    event="document_skipped",
                    status="skipped",
                    message="Source hash unchanged; existing normalized artifacts reused.",
                    document_id=record.document_id,
                    source_path=record.source_relpath,
                )
                continue

            _emit_pipeline_event(
                level=logging.INFO,
                stage="reading",
                event="document_start",
                status="started",
                message="Processing document",
                document_id=record.document_id,
                source_path=record.source_relpath,
            )
            try:
                result = _read_document(
                    record,
                    docs_raw=docs_raw,
                    llama_settings=llama_settings_override,
                    event_logger=event_logger,
                )
                platform_context = (
                    platform_context_resolver(record)
                    if platform_context_resolver is not None
                    else None
                )
                metadata, bundle = _write_success_artifacts(
                    record=record,
                    result=result,
                    docs_raw=docs_raw,
                    docs_normalized=output_root,
                    corpus_version=corpus_version,
                    pipeline_version=pipeline_version,
                    classification_review_threshold=classification_review_threshold,
                    ocr_review_threshold=ocr_review_threshold,
                    platform_context=platform_context,
                )
                bundle_manifests.append(bundle)
                record.processing_status = metadata.processing_status
                record.ocr_confidence = metadata.ocr_confidence
                document_duration_ms = measure_duration_ms(document_started_at)
                _emit_pipeline_event(
                    level=logging.INFO,
                    stage="normalization",
                    event="document_normalization_completed",
                    status="completed",
                    message="Document normalization completed",
                    document_id=record.document_id,
                    source_path=record.source_relpath,
                    duration_ms=document_duration_ms,
                    metrics={
                        "page_count": result.page_count,
                        "warning_count": len(result.warnings),
                    },
                    attributes={"processing_status": metadata.processing_status},
                )
                _emit_pipeline_event(
                    level=logging.INFO,
                    stage="validation",
                    event="document_validation_completed",
                    status="warning" if metadata.processing_status == "needs_review" else "completed",
                    message="Document validation completed",
                    document_id=record.document_id,
                    source_path=record.source_relpath,
                    duration_ms=document_duration_ms,
                    metrics={
                        "page_count": result.page_count,
                        "warning_count": len(result.warnings),
                        "review_reason_count": len(result.review_reasons),
                    },
                    attributes={
                        "processing_status": metadata.processing_status,
                        "review_reason_count": len(result.review_reasons),
                    },
                )
                if metadata.processing_status == "needs_review":
                    summary["needs_review"] += 1
                    needs_review.append(
                        {
                            "document_id": record.document_id,
                            "source_relpath": record.source_relpath,
                            "reasons": result.review_reasons,
                            "stage": "reading",
                            "recommended_action": "Revisar advertencias de extracción antes de indexar.",
                            "review_status": "pending",
                        }
                    )
                    _emit_pipeline_event(
                        level=logging.WARNING,
                        stage="review",
                        event="document_review_required",
                        status="warning",
                        message="Document requires human review",
                        document_id=record.document_id,
                        source_path=record.source_relpath,
                        duration_ms=document_duration_ms,
                        metrics={
                            "warning_count": len(result.warnings),
                            "review_reason_count": len(result.review_reasons),
                        },
                        attributes={
                            "processing_status": metadata.processing_status,
                            "review_status": "pending",
                        },
                    )
                else:
                    summary["processed"] += 1
                run_documents.append(
                    _run_document(
                        record,
                        document_status=record.processing_status,
                        disposition=record.processing_status,
                        warnings=result.warnings,
                    )
                )
                _emit_pipeline_event(
                    level=logging.INFO,
                    stage="output_generation",
                    event="document_finished",
                    status=record.processing_status,
                    message="Document processed",
                    document_id=record.document_id,
                    source_path=record.source_relpath,
                    duration_ms=document_duration_ms,
                )
            except Exception as exc:
                if isinstance(exc, OcrDependencyError):
                    reasons = exc.reasons
                elif _is_cloud_pdf_failure(record, llama_settings_override):
                    reasons = ["llama_cloud_provider_error"]
                elif record.detected_extension == ".pdf":
                    reasons = ["pdf_extractor_unconfigured"]
                else:
                    reasons = ["processing_error"]
                reason = reasons[0]
                status = "needs_review" if record.detected_extension == ".pdf" else "failed"
                record.processing_status = status
                summary[status] += 1
                target = needs_review if status == "needs_review" else errors
                target.append(
                    {
                        "document_id": record.document_id,
                        "source_relpath": record.source_relpath,
                        "reasons": reasons,
                        "stage": "ocr" if isinstance(exc, OcrDependencyError) else "reading",
                        "recommended_action": _failure_recommendation(reason, exc),
                        "review_status": "pending",
                        "error": str(exc),
                    }
                )
                run_documents.append(
                    _run_document(
                        record,
                        document_status=status,
                        disposition=status,
                        warnings=reasons,
                    )
                )
                _emit_pipeline_event(
                    level=logging.ERROR if status == "failed" else logging.WARNING,
                    stage="reading",
                    event="document_failed",
                    status=status,
                    message=str(exc),
                    document_id=record.document_id,
                    source_path=record.source_relpath,
                    warning_code=reason,
                    duration_ms=measure_duration_ms(document_started_at),
                    exception=exc,
                )

        write_inventory(manifests_dir / "inventory.json", records)
        dump_json(
            manifests_dir / f"{run_id}.json",
            RunManifest(
                schema_version="2.0",
                run_id=run_id,
                timestamp=_now(),
                fingerprints={},
                summary=summary,
                documents=run_documents,
                bundles=bundle_manifests,
            ),
        )
        dump_json(
            manifests_dir / "needs_review.json",
            ReviewManifest(
                schema_version="2.0",
                run_id=run_id,
                generated_at=_now(),
                items=[
                    ReviewItem(
                        schema_version="2.0",
                        document_id=item["document_id"],
                        source_relpath=item["source_relpath"],
                        reasons=item["reasons"],
                        details=[item.get("recommended_action", "")],
                    )
                    for item in needs_review
                ],
            ),
        )
        dump_json(
            manifests_dir / "errors.json",
            ErrorManifest(
                schema_version="2.0",
                run_id=run_id,
                generated_at=_now(),
                items=[
                    ErrorItem(
                        schema_version="2.0",
                        document_id=item.get("document_id"),
                        source_relpath=item.get("source_relpath"),
                        stage=item["stage"],
                        error_type=item["reasons"][0],
                        message=item.get("error", item["reasons"][0]),
                        retryable=False,
                    )
                    for item in errors
                ],
            ),
        )
        validation = validate_normalized_tree(output_root, raw_root=docs_raw, run_id=run_id)
        dump_json(manifests_dir / f"validation_{run_id}.json", validation)
        _emit_pipeline_event(
            level=logging.INFO,
            stage="validation",
            event="pipeline_validation_completed",
            status="completed",
            message="Pipeline validation completed",
            metrics={
                "document_count": len(records),
                "processed_count": summary["processed"],
                "needs_review_count": summary["needs_review"],
                "skipped_count": summary["skipped"],
                "failed_count": summary["failed"],
            },
            attributes={"validation_status": validation.status},
        )
        if promote:
            if validation.status != "passed":
                raise PromotionError("promotion requires structural validation to pass")
            _emit_pipeline_event(
                level=logging.INFO,
                stage="promotion",
                event="document_promotion_started",
                status="started",
                message="Promotion started",
                metrics={"document_count": len(records)},
                attributes={"validation_status": validation.status},
            )
            promote_candidate(
                output_root,
                docs_normalized,
                {
                    "structural_status": validation.status,
                    "golden_status": golden_status,
                    "run_id": run_id,
                },
            )
            _emit_pipeline_event(
                level=logging.INFO,
                stage="promotion",
                event="document_promotion_completed",
                status="completed",
                message="Promotion completed",
                metrics={"document_count": len(records)},
                attributes={"validation_status": validation.status},
            )
        _emit_pipeline_event(
            level=logging.INFO,
            stage="pipeline",
            event="pipeline_run_completed",
            status="completed",
            message="Pipeline run completed",
            duration_ms=measure_duration_ms(started_at),
            metrics={
                "document_count": len(records),
                "processed_count": summary["processed"],
                "needs_review_count": summary["needs_review"],
                "skipped_count": summary["skipped"],
                "failed_count": summary["failed"],
            },
            attributes={
                "validation_status": validation.status,
                "promoted": promote and validation.status == "passed",
            },
        )
        return summary
    except Exception as exc:
        _emit_pipeline_event(
            level=logging.ERROR,
            stage="pipeline",
            event="pipeline_run_failed",
            status="failed",
            message=str(exc),
            duration_ms=measure_duration_ms(started_at),
            metrics={
                "processed_count": summary["processed"],
                "needs_review_count": summary["needs_review"],
                "skipped_count": summary["skipped"],
                "failed_count": summary["failed"],
            },
            exception=exc,
        )
        raise
