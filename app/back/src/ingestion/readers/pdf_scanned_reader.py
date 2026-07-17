from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Dict, List, Protocol

from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import OcrArtifact, OcrPage, PageRecord


class OcrEngine(Protocol):
    engine: str
    engine_version: str
    language: str

    def extract_pages(self, source_path: Path) -> List[Dict]:
        ...


class MissingOcrEngine:
    engine = "ocrmypdf"
    engine_version = "unavailable"
    language = "spa"

    def extract_pages(self, source_path: Path) -> List[Dict]:
        raise RuntimeError("No OCR engine configured. Install OCRmyPDF/Tesseract or inject an engine.")


class PdfScannedReader:
    def __init__(self, ocr_engine: OcrEngine = None, low_confidence_threshold: float = 0.70) -> None:
        self.ocr_engine = ocr_engine or MissingOcrEngine()
        self.low_confidence_threshold = low_confidence_threshold

    def read(self, source_path: Path) -> ReadResult:
        ocr_pages = self.ocr_engine.extract_pages(source_path)
        pages: List[PageRecord] = []
        ocr_records: List[OcrPage] = []
        markdown_parts: List[str] = []
        review_reasons: List[str] = []

        for page in ocr_pages:
            text_raw = str(page.get("text", ""))
            text_normalized = normalize_text(text_raw)
            confidence = float(page.get("confidence", 0.0))
            contains_handwriting = bool(page.get("contains_handwriting", False))
            warnings: List[str] = []
            if confidence < self.low_confidence_threshold:
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
                    has_handwriting_warning=contains_handwriting,
                    warnings=warnings,
                )
            )
            words = text_normalized.split()
            ocr_records.append(
                OcrPage(
                    page_number=page_number,
                    confidence=confidence,
                    word_count=len(words),
                    low_confidence_word_count=0,
                    deskew_applied=bool(page.get("deskew_applied", False)),
                    rotation_detected_degrees=int(page.get("rotation_detected_degrees", 0)),
                    contains_handwriting=contains_handwriting,
                    warnings=warnings,
                )
            )

        overall = mean([page.confidence for page in ocr_records]) if ocr_records else 0.0
        ocr = OcrArtifact(
            document_id="pending",
            engine=getattr(self.ocr_engine, "engine", "tesseract"),
            engine_version=getattr(self.ocr_engine, "engine_version", "unknown"),
            language=getattr(self.ocr_engine, "language", "spa"),
            overall_confidence=overall,
            pages=ocr_records,
        )
        return ReadResult(
            extraction_method="ocr",
            markdown="\n\n".join(markdown_parts).strip(),
            pages=pages,
            warnings=review_reasons,
            review_reasons=review_reasons,
            ocr=ocr,
        )
