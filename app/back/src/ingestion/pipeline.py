from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import ValidationError

from ingestion.classification.rules import classify_document
from ingestion.document_control.extractor import extract_document_control
from ingestion.inventory.scanner import scan_docs_raw
from ingestion.logging.jsonl import JsonlLogger
from ingestion.manifests.writer import dump_json, write_inventory
from ingestion.promotion import promote_candidate
from ingestion.readers.base import ReadResult
from ingestion.ocr.ocrmypdf_engine import OcrDependencyError, OcrMyPdfEngine
from ingestion.readers.markdown_reader import MarkdownReader
from ingestion.readers.pdf_digital_reader import PdfDigitalReader
from ingestion.readers.pdf_scanned_reader import PdfScannedReader
from ingestion.schemas.artifacts import MetadataArtifact, PagesArtifact
from ingestion.schemas.common import ConfidenceMetric, Evidence, Observation
from ingestion.schemas.inventory import InventoryRecord
from ingestion.schemas.manifests import ErrorManifest, ErrorItem, ReviewManifest, ReviewItem, RunDocument, RunManifest
from ingestion.validation.normalized import validate_normalized_tree


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


def _build_metadata(
    *,
    record: InventoryRecord,
    normalized_md: Path,
    result: ReadResult,
    corpus_version: str,
    pipeline_version: str,
    classification_review_threshold: float,
) -> MetadataArtifact:
    document_control = extract_document_control(result.pages, record.document_name)
    classification = classify_document(record.source_relpath, result.pages, document_control)
    ocr_confidence = (
        result.ocr.document_confidence if result.ocr is not None else ConfidenceMetric(kind="unavailable", value=None)
    )
    handwriting = _handwriting_observation(result)
    tables = (
        Observation(
            status="detected",
            value=True,
            method="reader_tables",
            evidence=[Evidence(source="tables_artifact")],
            warnings=["table_evidence_available_in_tables_artifact"],
        )
        if result.tables is not None and result.tables.table_count > 0
        else Observation(status="not_detected", value=False, method="reader_tables")
    )
    forms = Observation(status="not_evaluated", value=None)
    warnings = list(result.warnings)
    review_reasons = list(result.review_reasons)
    if (classification.document_type_confidence.value or 0) < classification_review_threshold:
        warnings.append("ambiguous_classification")
        review_reasons.append("ambiguous_classification")
    result.review_reasons = review_reasons
    result.warnings = warnings
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
        source_hash=record.content_hash,
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        processing_status="needs_review" if result.review_reasons else "processed",
        review_reasons=result.review_reasons,
        warnings=result.warnings,
        processed_at=_now(),
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
) -> MetadataArtifact:
    output_base = _output_base_for_record(record, docs_normalized)
    normalized_md = output_base.with_suffix(".md")
    metadata_path = output_base.with_suffix(".metadata.json")
    pages_path = output_base.with_suffix(".pages.json")
    normalized_md.parent.mkdir(parents=True, exist_ok=True)

    _set_artifact_document_id(result, record.document_id)
    metadata = _build_metadata(
        record=record,
        normalized_md=normalized_md,
        result=result,
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        classification_review_threshold=classification_review_threshold,
    )
    pages = PagesArtifact(schema_version="2.0", document_id=record.document_id, page_count=result.page_count, pages=result.pages)

    normalized_md.write_text(_front_matter(metadata) + result.markdown + "\n", encoding="utf-8")
    dump_json(metadata_path, metadata)
    dump_json(pages_path, pages)
    if result.ocr is not None:
        dump_json(output_base.with_suffix(".ocr.json"), result.ocr)
    if result.tables is not None:
        dump_json(output_base.with_suffix(".tables.json"), result.tables)
    return metadata


def _handwriting_observation(result: ReadResult) -> Observation:
    if result.ocr is None:
        return Observation(status="not_evaluated", value=None)
    for page in result.ocr.pages:
        if page.handwriting.status == "detected":
            return page.handwriting
    return Observation(status="not_detected", value=False, method="ocr_reader")


def _source_path_for_record(record: InventoryRecord, docs_raw: Optional[Path] = None) -> Path:
    if docs_raw is not None:
        return docs_raw / record.source_relpath
    if record.legacy_path:
        return Path(record.legacy_path)
    return Path(record.source_relpath)


def _read_document(
    record: InventoryRecord,
    pdf_reader_factory=None,
    ocr_engine=None,
    docs_raw: Optional[Path] = None,
) -> ReadResult:
    source_path = _source_path_for_record(record, docs_raw)
    if record.detected_extension == ".md":
        return MarkdownReader().read(source_path)
    if record.detected_extension == ".pdf":
        pdf_reader_or_extractor = pdf_reader_factory() if pdf_reader_factory else PdfDigitalReader()
        pdf_reader = (
            pdf_reader_or_extractor
            if hasattr(pdf_reader_or_extractor, "read")
            else PdfDigitalReader(extractor=pdf_reader_or_extractor)
        )
        try:
            return pdf_reader.read(source_path)
        except RuntimeError as exc:
            fallback_signals = (
                "No PDF extractor configured",
                "PDF text layer insufficient",
                "PDF text extraction failed",
            )
            if not any(signal in str(exc) for signal in fallback_signals):
                raise
            return PdfScannedReader(ocr_engine=ocr_engine or OcrMyPdfEngine()).read(source_path)
    raise ValueError(f"Unsupported format: {record.detected_extension or 'unknown'}")


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
) -> Dict[str, int]:
    run_id = run_id or "run_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    output_root = staging_root or docs_normalized
    manifests_dir = output_root / "_manifests"
    logger = JsonlLogger(manifests_dir / f"{run_id}_details.log", run_id)
    previous_records = _load_previous_inventory(manifests_dir / "inventory.json")
    records = scan_docs_raw(docs_raw, corpus_version=corpus_version, pipeline_version=pipeline_version)
    if only_sources is not None:
        selected = set(only_sources)
        records = [record for record in records if record.source_relpath in selected]
    summary = {"processed": 0, "failed": 0, "needs_review": 0, "skipped": 0}
    errors: List[dict] = []
    needs_review: List[dict] = []
    run_documents: List[dict] = []

    for record in records:
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
            logger.event(
                stage="inventory",
                event="document_skipped",
                status="skipped",
                message="Source hash unchanged; existing normalized artifacts reused.",
                document_id=record.document_id,
                source_path=record.source_relpath,
            )
            continue

        logger.event(
            stage="reading",
            event="document_start",
            status="started",
            message="Processing document",
            document_id=record.document_id,
            source_path=record.source_relpath,
        )
        try:
            result = _read_document(record, docs_raw=docs_raw)
            metadata = _write_success_artifacts(
                record=record,
                result=result,
                docs_raw=docs_raw,
                    docs_normalized=output_root,
                corpus_version=corpus_version,
                pipeline_version=pipeline_version,
                classification_review_threshold=classification_review_threshold,
            )
            record.processing_status = metadata.processing_status
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
            logger.event(
                stage="output_generation",
                event="document_finished",
                status=record.processing_status,
                message="Document processed",
                document_id=record.document_id,
                source_path=record.source_relpath,
            )
        except Exception as exc:
            if isinstance(exc, OcrDependencyError):
                reasons = exc.reasons
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
                    "recommended_action": "Instalar/configurar OCRmyPDF y el idioma spa de Tesseract."
                    if isinstance(exc, OcrDependencyError)
                    else "Configurar extractor PDF/OCR para este documento.",
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
            logger.event(
                stage="reading",
                event="document_failed",
                status=status,
                message=str(exc),
                document_id=record.document_id,
                source_path=record.source_relpath,
                warning_code=reason,
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
            bundles=[],
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
    if promote:
        promote_candidate(
            output_root,
            docs_normalized,
            {
                "structural_status": validation.status,
                "golden_status": "passed",
                "run_id": run_id,
            },
        )
    return summary
