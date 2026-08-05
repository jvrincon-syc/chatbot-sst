from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Protocol

from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import OcrArtifact, OcrPage, PageRecord
from ingestion.schemas.common import ConfidenceMetric, Evidence, MeasuredValue, Observation
from ingestion.structure.forms import FormExtractor
from ingestion.structure.tables import TableExtractor


class OcrEngine(Protocol):
    engine: str
    engine_version: str
    language: str

    def extract_pages(self, source_path: Path) -> List[Dict]:
        ...


class MissingOcrEngine:
    engine = "tesseract"
    engine_version = "unavailable"
    language = "spa"

    def extract_pages(self, source_path: Path) -> List[Dict]:
        raise RuntimeError("No OCR engine configured. Install Tesseract/PDFium or inject an engine.")


class PdfScannedReader:
    def __init__(
        self,
        ocr_engine: OcrEngine = None,
        low_confidence_threshold: float = 0.70,
        table_extractor: TableExtractor | None = None,
        form_extractor: FormExtractor | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine or MissingOcrEngine()
        self.low_confidence_threshold = low_confidence_threshold
        self.table_extractor = table_extractor or TableExtractor(method="ocr_text")
        self.form_extractor = form_extractor or FormExtractor(method="ocr_text")

    def read(self, source_path: Path) -> ReadResult:
        ocr_pages = self.ocr_engine.extract_pages(source_path)
        pages: List[PageRecord] = []
        ocr_records: List[OcrPage] = []
        markdown_parts: List[str] = []
        review_reasons: List[str] = []

        for page in ocr_pages:
            text_raw = str(page.get("text", ""))
            text_normalized = normalize_text(text_raw)
            confidence, confidence_warnings = _confidence_from_raw(
                page.get("confidence"),
                engine=getattr(self.ocr_engine, "engine", "tesseract"),
                engine_version=getattr(self.ocr_engine, "engine_version", "unknown"),
            )
            contains_handwriting = page.get("contains_handwriting") is True
            warnings: List[str] = []
            warnings.extend(confidence_warnings)
            if confidence.value is not None and confidence.value < self.low_confidence_threshold:
                warnings.append("low_ocr_confidence")
            if contains_handwriting:
                warnings.append("possible_handwriting")
            review_reasons.extend(reason for reason in warnings if reason not in review_reasons)
            page_number = int(page.get("page_number", len(pages) + 1))
            markdown_parts.append(f"<!-- page: {page_number} -->\n\n{text_normalized}")
            pages.append(
                PageRecord(
                    page_number=page_number,
                    text_raw=text_raw,
                    text_normalized=text_normalized,
                    extraction_method="ocr",
                    ocr_confidence=confidence,
                    warnings=warnings,
                )
            )
            words = text_normalized.split()
            ocr_records.append(
                OcrPage(
                    page_number=page_number,
                    confidence=confidence,
                    word_count=len(words),
                    words=[],
                    low_confidence_word_count=None,
                    deskew=_feature_observation(page.get("deskew_applied"), "deskew_applied"),
                    rotation=_rotation_value(page.get("rotation_detected_degrees")),
                    handwriting=_feature_observation(contains_handwriting, "contains_handwriting"),
                    warnings=warnings,
                )
            )

        measured_values = [page.confidence.value for page in ocr_records if page.confidence.value is not None]
        document_confidence = (
            ConfidenceMetric(
                kind="estimated",
                value=mean(measured_values),
                engine=getattr(self.ocr_engine, "engine", "tesseract"),
                engine_version=getattr(self.ocr_engine, "engine_version", "unknown"),
                method="page_confidence_average",
                warnings=["ocr_confidence_not_word_measured"],
            )
            if measured_values
            else ConfidenceMetric(kind="unavailable", value=None)
        )
        ocr = OcrArtifact(
            schema_version="2.0",
            document_id="pending",
            engine=getattr(self.ocr_engine, "engine", "tesseract"),
            engine_version=getattr(self.ocr_engine, "engine_version", "unknown"),
            language=getattr(self.ocr_engine, "language", "spa"),
            document_confidence=document_confidence,
            pages=ocr_records,
        )
        tables = self.table_extractor.evaluate_pages(pages)
        forms = self.form_extractor.evaluate_pages(pages)
        return ReadResult(
            extraction_method="ocr",
            markdown="\n\n".join(markdown_parts).strip(),
            pages=pages,
            warnings=review_reasons,
            review_reasons=review_reasons,
            ocr=ocr,
            tables=tables,
            forms=forms,
        )


def _confidence_from_raw(
    raw: Any,
    *,
    engine: str,
    engine_version: str,
) -> tuple[ConfidenceMetric, list[str]]:
    if raw is None:
        return ConfidenceMetric(kind="unavailable", value=None), ["ocr_confidence_unavailable"]
    if isinstance(raw, bool):
        return ConfidenceMetric(kind="unavailable", value=None), ["boolean_ocr_confidence_rejected"]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ConfidenceMetric(kind="unavailable", value=None), ["invalid_ocr_confidence_rejected"]
    if value < 0 or value > 1:
        return ConfidenceMetric(kind="unavailable", value=None), ["invalid_ocr_confidence_rejected"]
    return (
        ConfidenceMetric(
            kind="estimated",
            value=value,
            engine=engine,
            engine_version=engine_version,
            method="engine_page_confidence",
            warnings=["ocr_confidence_not_word_measured"],
        ),
        [],
    )


def _feature_observation(raw: Any, feature: str) -> Observation:
    if raw is True:
        return Observation(
            status="detected",
            value=True,
            method="engine_assertion",
            evidence=[Evidence(text=f"{feature}=true", source="ocr_engine")],
            warnings=["feature_detection_not_independently_measured"],
        )
    return Observation(status="not_evaluated", value=None)


def _rotation_value(raw: Any) -> MeasuredValue:
    if raw is None or isinstance(raw, bool):
        return MeasuredValue(status="unavailable", value=None)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return MeasuredValue(status="unavailable", value=None)
    return MeasuredValue(
        status="estimated",
        value=value,
        unit="degrees",
        method="engine_assertion",
        warnings=["rotation_not_independently_measured"],
    )
