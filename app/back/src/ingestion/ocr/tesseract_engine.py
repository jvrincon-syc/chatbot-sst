from __future__ import annotations

import csv
import subprocess
from io import StringIO
from pathlib import Path
from statistics import mean
from typing import Callable, Optional

import pypdfium2 as pdfium
from pydantic import Field

from ingestion.ocr.rasterizer import PageRasterizer, RasterRegion
from ingestion.schemas.artifacts import OcrPage, OcrWord
from ingestion.schemas.common import BBox, ConfidenceMetric, MeasuredValue, Observation, StrictModel


class TesseractCapabilityError(RuntimeError):
    def __init__(self, message: str, reasons: list[str]) -> None:
        super().__init__(message)
        self.reasons = reasons


class OcrRegionResult(StrictModel):
    page_number: int = Field(ge=1)
    text: str
    words: list[OcrWord]
    confidence: ConfidenceMetric
    low_confidence_word_count: int = Field(ge=0)
    bbox: Optional[BBox] = None
    warnings: list[str] = Field(default_factory=list)


class TesseractEngine:
    engine = "tesseract"

    def __init__(
        self,
        *,
        tesseract_cmd: str = "tesseract",
        language: str = "spa",
        engine_version: str = "unknown",
        runner: Callable = subprocess.run,
        low_confidence_threshold: float = 0.70,
    ) -> None:
        self.tesseract_cmd = tesseract_cmd
        self.language = language
        self.engine_version = engine_version
        self.runner = runner
        self.low_confidence_threshold = low_confidence_threshold

    def recognize(self, region: RasterRegion) -> OcrRegionResult:
        command = [
            self.tesseract_cmd,
            str(region.image_path),
            "stdout",
            "-l",
            self.language,
            "tsv",
        ]
        try:
            result = self.runner(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise TesseractCapabilityError("Tesseract is not installed.", ["tesseract_unavailable"]) from exc
        except subprocess.CalledProcessError as exc:
            raise TesseractCapabilityError("Tesseract failed.", ["tesseract_failed"]) from exc
        return parse_tesseract_tsv(
            result.stdout,
            page_number=region.page_number,
            engine_version=self.engine_version,
            region_bbox=region.bbox,
            low_confidence_threshold=self.low_confidence_threshold,
        )


class TesseractPdfEngine:
    engine = "tesseract"

    def __init__(
        self,
        *,
        region_engine: TesseractEngine,
        rasterizer: PageRasterizer | None = None,
        page_count: Callable[[Path], int] | None = None,
    ) -> None:
        self.region_engine = region_engine
        self.rasterizer = rasterizer or PageRasterizer()
        self.page_count = page_count or _pdf_page_count
        self.engine_version = region_engine.engine_version
        self.language = region_engine.language

    def extract_pages(self, source_path: Path) -> list[dict]:
        pages: list[dict] = []
        for page_number in range(1, self.page_count(source_path) + 1):
            region = self.rasterizer.render(source_path, page_number, None)
            try:
                result = self.region_engine.recognize(region)
            finally:
                region.image_path.unlink(missing_ok=True)
            pages.append(
                {
                    "page_number": page_number,
                    "text": result.text,
                    "confidence": result.confidence.value,
                    "contains_handwriting": None,
                    "deskew_applied": None,
                    "rotation_detected_degrees": None,
                }
            )
        return pages


def _pdf_page_count(path: Path) -> int:
    return len(pdfium.PdfDocument(str(path)))


def parse_tesseract_tsv(
    tsv_text: str,
    *,
    page_number: int,
    engine: str = "tesseract",
    engine_version: str = "unknown",
    region_bbox: BBox | None = None,
    low_confidence_threshold: float = 0.70,
) -> OcrRegionResult:
    reader = csv.DictReader(StringIO(tsv_text), delimiter="\t")
    words: list[OcrWord] = []
    confidences: list[float] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        raw_confidence = row.get("conf")
        if raw_confidence is None or raw_confidence == "":
            continue
        try:
            confidence_0_100 = float(raw_confidence)
        except ValueError:
            continue
        if confidence_0_100 < 0:
            continue
        confidence = max(0.0, min(confidence_0_100 / 100.0, 1.0))
        bbox = BBox(
            x0=_float_cell(row, "left"),
            top=_float_cell(row, "top"),
            x1=_float_cell(row, "left") + _float_cell(row, "width"),
            bottom=_float_cell(row, "top") + _float_cell(row, "height"),
            coordinate_system="pixels",
        )
        words.append(OcrWord(text=text, bbox=bbox, confidence=confidence))
        confidences.append(confidence)

    if confidences:
        metric = ConfidenceMetric(
            kind="measured",
            value=mean(confidences),
            engine=engine,
            engine_version=engine_version,
            unit="mean_word_confidence",
            sample_size=len(confidences),
        )
    else:
        metric = ConfidenceMetric(kind="unavailable", value=None)

    return OcrRegionResult(
        page_number=page_number,
        text=" ".join(word.text for word in words),
        words=words,
        confidence=metric,
        low_confidence_word_count=sum(
            1 for value in confidences if value < low_confidence_threshold
        ),
        bbox=region_bbox,
    )


def ocr_page_from_region(result: OcrRegionResult) -> OcrPage:
    return OcrPage(
        page_number=result.page_number,
        words=result.words,
        confidence=result.confidence,
        word_count=len(result.words),
        low_confidence_word_count=result.low_confidence_word_count,
        deskew=Observation(status="not_evaluated", value=None),
        rotation=MeasuredValue(status="unavailable", value=None),
        handwriting=Observation(status="not_evaluated", value=None),
        warnings=result.warnings,
    )


def _float_cell(row: dict[str, str | None], key: str) -> float:
    raw = row.get(key)
    if raw is None:
        raise ValueError(f"Tesseract TSV row missing {key}")
    return float(raw)
