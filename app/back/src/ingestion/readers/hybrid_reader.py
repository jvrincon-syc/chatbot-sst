from __future__ import annotations

from pathlib import Path
from statistics import mean

from ingestion.coverage.analyzer import CoverageAnalyzer
from ingestion.normalization.text import normalize_text
from ingestion.ocr.rasterizer import PageRasterizer, RasterizationCapabilityError
from ingestion.ocr.tesseract_engine import OcrRegionResult
from ingestion.readers.base import ReadResult
from ingestion.readers.pdf_digital_reader import PdfDigitalReader
from ingestion.schemas.artifacts import OcrArtifact, OcrPage, PageRecord
from ingestion.schemas.common import ConfidenceMetric, MeasuredValue, Observation


class HybridReader:
    def __init__(
        self,
        *,
        digital_reader: PdfDigitalReader | None = None,
        coverage_analyzer: CoverageAnalyzer | None = None,
        rasterizer: PageRasterizer | None = None,
        ocr_engine=None,
    ) -> None:
        self.digital_reader = digital_reader or PdfDigitalReader()
        self.coverage_analyzer = coverage_analyzer or CoverageAnalyzer()
        self.rasterizer = rasterizer or PageRasterizer()
        self.ocr_engine = ocr_engine

    def read(self, source_path: Path) -> ReadResult:
        digital = self.digital_reader.read(source_path)
        ocr_results: list[OcrRegionResult] = []
        warnings = list(digital.warnings)
        review_reasons = list(digital.review_reasons)

        for page in digital.pages:
            assessment = self.coverage_analyzer.assess(page)
            for candidate in assessment.candidate_regions:
                if self.ocr_engine is None:
                    _append_once(warnings, "ocr_unavailable_for_uncovered_region")
                    _append_once(review_reasons, "ocr_unavailable_for_uncovered_region")
                    continue
                try:
                    region = self.rasterizer.render(
                        source_path,
                        candidate.page_number,
                        candidate.bbox,
                    )
                    ocr_results.append(self.ocr_engine.recognize(region))
                except RasterizationCapabilityError:
                    _append_once(warnings, "rasterizer_unavailable_for_uncovered_region")
                    _append_once(review_reasons, "rasterizer_unavailable_for_uncovered_region")

        if not ocr_results:
            digital.warnings = warnings
            digital.review_reasons = review_reasons
            return digital

        ocr_by_page: dict[int, list[OcrRegionResult]] = {}
        for result in ocr_results:
            ocr_by_page.setdefault(result.page_number, []).append(result)

        pages: list[PageRecord] = []
        markdown_parts: list[str] = []
        added_any = False
        for page in digital.pages:
            seen_text = {normalize_text(page.text_normalized)}
            additions: list[str] = []
            for result in ocr_by_page.get(page.page_number, []):
                normalized_result = normalize_text(result.text)
                if normalized_result and normalized_result not in seen_text:
                    additions.append(normalized_result)
                    seen_text.add(normalized_result)
            if additions:
                added_any = True
            text_normalized = normalize_text("\n".join([page.text_normalized, *additions]))
            confidence = _page_confidence(ocr_by_page.get(page.page_number, []))
            pages.append(
                page.model_copy(
                    update={
                        "text_normalized": text_normalized,
                        "extraction_method": "hybrid",
                        "ocr_confidence": confidence,
                    }
                )
            )
            markdown_parts.append(f"<!-- page: {page.page_number} -->\n\n{text_normalized}")

        if not added_any:
            digital.warnings = warnings
            digital.review_reasons = review_reasons
            return digital

        ocr_pages = _ocr_pages_from_regions(ocr_by_page, self.ocr_engine)
        ocr = OcrArtifact(
            schema_version="2.0",
            document_id="pending",
            engine="tesseract",
            engine_version=_engine_version(self.ocr_engine),
            language=getattr(self.ocr_engine, "language", None),
            document_confidence=_document_confidence(ocr_results, self.ocr_engine),
            pages=ocr_pages,
        )
        return ReadResult(
            extraction_method="hybrid",
            markdown="\n\n".join(markdown_parts).strip(),
            pages=pages,
            warnings=warnings,
            review_reasons=review_reasons,
            tables=digital.tables,
            forms=digital.forms,
            ocr=ocr,
        )


def _page_confidence(results: list[OcrRegionResult]) -> ConfidenceMetric:
    measured = [result.confidence.value for result in results if result.confidence.value is not None]
    if not measured:
        return ConfidenceMetric(kind="unavailable", value=None)
    return ConfidenceMetric(
        kind="estimated",
        value=mean(measured),
        method="region_ocr_confidence_average",
        warnings=["page_confidence_aggregated_from_regions"],
    )


def _document_confidence(results: list[OcrRegionResult], engine) -> ConfidenceMetric:
    values: list[float] = []
    for result in results:
        values.extend(word.confidence for word in result.words if word.confidence is not None)
    if not values:
        return ConfidenceMetric(kind="unavailable", value=None)
    return ConfidenceMetric(
        kind="measured",
        value=mean(values),
        engine="tesseract",
        engine_version=_engine_version(engine),
        unit="mean_word_confidence",
        sample_size=len(values),
    )


def _ocr_pages_from_regions(
    ocr_by_page: dict[int, list[OcrRegionResult]],
    engine,
) -> list[OcrPage]:
    pages: list[OcrPage] = []
    for page_number in sorted(ocr_by_page):
        results = ocr_by_page[page_number]
        words = [word for result in results for word in result.words]
        confidence = _word_confidence(words, engine)
        pages.append(
            OcrPage(
                page_number=page_number,
                words=words,
                confidence=confidence,
                word_count=len(words),
                low_confidence_word_count=sum(result.low_confidence_word_count for result in results),
                deskew=Observation(status="not_evaluated", value=None),
                rotation=MeasuredValue(status="unavailable", value=None),
                handwriting=Observation(status="not_evaluated", value=None),
                warnings=sorted({warning for result in results for warning in result.warnings}),
            )
        )
    return pages


def _word_confidence(words, engine) -> ConfidenceMetric:
    values = [word.confidence for word in words if word.confidence is not None]
    if not values:
        return ConfidenceMetric(kind="unavailable", value=None)
    return ConfidenceMetric(
        kind="measured",
        value=mean(values),
        engine="tesseract",
        engine_version=_engine_version(engine),
        unit="mean_word_confidence",
        sample_size=len(values),
    )


def _engine_version(engine) -> str:
    return getattr(engine, "engine_version", "unknown")


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
