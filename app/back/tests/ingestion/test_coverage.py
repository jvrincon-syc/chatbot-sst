from types import SimpleNamespace

from ingestion.coverage.analyzer import CoverageAnalyzer
from ingestion.schemas.common import BBox, PageBlock


def box(x0: float, top: float, x1: float, bottom: float) -> BBox:
    return BBox(x0=x0, top=top, x1=x1, bottom=bottom, coordinate_system="pdf_points")


def image_block(block_id: str, bbox: BBox, *, role: str | None = "image") -> PageBlock:
    return PageBlock(
        block_id=block_id,
        text="",
        bbox=bbox,
        extraction_method="pdf_digital",
        role=role,
    )


def test_coverage_analyzer_flags_image_regions_on_sparse_pages() -> None:
    page = SimpleNamespace(
        page_number=13,
        width=612,
        height=792,
        text_normalized="Pocas palabras",
        blocks=[image_block("instruction_image", box(40, 120, 560, 620))],
    )

    assessment = CoverageAnalyzer(sparse_page_word_threshold=20).assess(page)

    assert assessment.status == "partial"
    assert assessment.candidate_regions[0].reason == "image_region_on_sparse_page"
    assert assessment.candidate_regions[0].source_block_id == "instruction_image"


def test_coverage_analyzer_does_not_let_document_word_count_hide_sparse_page() -> None:
    page = SimpleNamespace(
        page_number=14,
        width=612,
        height=792,
        text_normalized="texto",
        blocks=[image_block("matrix", box(30, 150, 580, 700))],
    )

    assessment = CoverageAnalyzer(sparse_page_word_threshold=5).assess(page)

    assert assessment.word_count == 1
    assert assessment.status == "partial"


def test_coverage_analyzer_ignores_logo_like_images() -> None:
    page = SimpleNamespace(
        page_number=1,
        width=612,
        height=792,
        text_normalized="",
        blocks=[image_block("logo", box(20, 20, 90, 60), role="logo")],
    )

    assessment = CoverageAnalyzer().assess(page)

    assert assessment.status == "complete"
    assert assessment.candidate_regions == []
