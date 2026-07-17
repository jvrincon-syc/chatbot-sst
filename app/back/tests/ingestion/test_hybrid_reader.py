from pathlib import Path

from ingestion.coverage.analyzer import CoverageAnalyzer
from ingestion.ocr.rasterizer import RasterRegion
from ingestion.ocr.tesseract_engine import OcrRegionResult, parse_tesseract_tsv
from ingestion.readers.base import ReadResult
from ingestion.readers.hybrid_reader import HybridReader
from ingestion.schemas.artifacts import PageRecord
from ingestion.schemas.common import BBox, ConfidenceMetric, PageBlock


def box(x0: float, top: float, x1: float, bottom: float) -> BBox:
    return BBox(x0=x0, top=top, x1=x1, bottom=bottom, coordinate_system="pdf_points")


class FakeDigitalReader:
    def read(self, source_path: Path) -> ReadResult:
        return ReadResult(
            extraction_method="pdf_digital",
            markdown="<!-- page: 1 -->\n\nTexto digital",
            pages=[
                PageRecord(
                    page_number=1,
                    text_raw="Texto digital",
                    text_normalized="Texto digital",
                    extraction_method="pdf_digital",
                    blocks=[
                        PageBlock(
                            block_id="image_1",
                            text="",
                            bbox=box(30, 150, 580, 700),
                            extraction_method="pdf_digital",
                            role="image",
                        ),
                        PageBlock(
                            block_id="image_2",
                            text="",
                            bbox=box(40, 710, 500, 760),
                            extraction_method="pdf_digital",
                            role="image",
                        )
                    ],
                    ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
                )
            ],
        )


class FakeRasterizer:
    def render(self, path: Path, page_number: int, clip: BBox, dpi: int | None = None) -> RasterRegion:
        return RasterRegion(
            image_path=path.with_suffix(".png"),
            page_number=page_number,
            bbox=clip,
            dpi=dpi or 300,
            width=100,
            height=100,
        )


class FakeRegionOcr:
    language = "spa"
    engine_version = "5.5.2"

    def recognize(self, region: RasterRegion) -> OcrRegionResult:
        return parse_tesseract_tsv(
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t10\t20\t10\t90\tOCR\n",
            page_number=region.page_number,
            engine_version=self.engine_version,
            region_bbox=region.bbox,
        )


def test_hybrid_reader_ocr_only_uncovered_regions_and_marks_hybrid(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = HybridReader(
        digital_reader=FakeDigitalReader(),
        coverage_analyzer=CoverageAnalyzer(sparse_page_word_threshold=20),
        rasterizer=FakeRasterizer(),
        ocr_engine=FakeRegionOcr(),
    ).read(source)

    assert result.extraction_method == "hybrid"
    assert result.pages[0].extraction_method == "hybrid"
    assert "Texto digital" in result.markdown
    assert "OCR" in result.markdown
    assert result.markdown.count("OCR") == 1
    assert result.ocr is not None
    assert len(result.ocr.pages) == 1
    assert result.ocr.pages[0].word_count == 2
    assert result.ocr.document_confidence.kind == "measured"
    assert result.pages[0].ocr_confidence.value == 0.9


def test_hybrid_reader_requires_review_when_ocr_unavailable_for_substantive_gap(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = HybridReader(
        digital_reader=FakeDigitalReader(),
        coverage_analyzer=CoverageAnalyzer(sparse_page_word_threshold=20),
        rasterizer=FakeRasterizer(),
        ocr_engine=None,
    ).read(source)

    assert result.extraction_method == "pdf_digital"
    assert "ocr_unavailable_for_uncovered_region" in result.review_reasons
    assert result.ocr is None
