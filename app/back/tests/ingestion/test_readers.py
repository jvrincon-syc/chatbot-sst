from __future__ import annotations

from pathlib import Path

from ingestion.ocr.mock_engine import MockOcrEngine
from ingestion.readers.markdown_reader import MarkdownReader
from ingestion.readers.pdf_digital_reader import PdfDigitalReader, PdfPage
from ingestion.schemas.common import BBox, PageBlock
from ingestion.readers.pdf_scanned_reader import PdfScannedReader


class FakePdfExtractor:
    def extract_pages(self, source_path: Path) -> list[PdfPage]:
        return [
            PdfPage(page_number=1, text="Titulo\n\nPrimer parrafo", tables=[]),
            PdfPage(page_number=2, text="Segundo parrafo", tables=[]),
        ]


def test_markdown_reader_preserves_title_list_and_table(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"
    source.write_text(
        "# Manual\n\n- item uno\n- item dos\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
        encoding="utf-8",
    )

    result = MarkdownReader().read(source)

    assert result.extraction_method == "markdown"
    assert result.page_count == 1
    assert result.pages[0].text_raw.startswith("# Manual")
    assert "| A | B |" in result.pages[0].text_normalized
    assert result.pages[0].ocr_confidence.kind == "unavailable"
    assert result.warnings == []


def test_markdown_reader_missing_title_is_warning_not_review_blocker(tmp_path: Path) -> None:
    source = tmp_path / "nota.md"
    source.write_text("Contenido sin encabezado", encoding="utf-8")

    result = MarkdownReader().read(source)

    assert result.warnings == ["missing_title"]
    assert result.review_reasons == []


def test_pdf_digital_reader_uses_injected_extractor_and_adds_page_markers(tmp_path: Path) -> None:
    source = tmp_path / "documento.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = PdfDigitalReader(extractor=FakePdfExtractor(), min_extractable_words=1).read(source)

    assert result.extraction_method == "pdf_digital"
    assert result.page_count == 2
    assert "<!-- page: 1 -->" in result.markdown
    assert "<!-- page: 2 -->" in result.markdown
    assert result.pages[1].page_number == 2
    assert result.pages[0].ocr_confidence.kind == "unavailable"


def test_pdf_digital_reader_evaluates_table_and_form_capabilities(tmp_path: Path) -> None:
    class StructuredPdfExtractor:
        def extract_pages(self, source_path: Path) -> list[PdfPage]:
            return [
                PdfPage(
                    page_number=1,
                    text="FORMATO DE QUEJA\nNombre:\nDescripcion:",
                    tables=[
                        {
                            "bbox": (20, 100, 500, 180),
                            "rows": [
                                ["Campo", "Valor"],
                                ["Nombre", ""],
                            ],
                        }
                    ],
                    blocks=[
                        PageBlock(
                            block_id="name",
                            text="Nombre:",
                            bbox=BBox(
                                x0=20,
                                top=200,
                                x1=90,
                                bottom=218,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="label",
                        ),
                        PageBlock(
                            block_id="description",
                            text="Descripcion:",
                            bbox=BBox(
                                x0=20,
                                top=240,
                                x1=120,
                                bottom=258,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="label",
                        ),
                        PageBlock(
                            block_id="blank",
                            text="",
                            bbox=BBox(
                                x0=130,
                                top=240,
                                x1=500,
                                bottom=300,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="blank_area",
                        ),
                    ],
                )
            ]

    source = tmp_path / "structured.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = PdfDigitalReader(
        extractor=StructuredPdfExtractor(),
        min_extractable_words=1,
    ).read(source)

    assert result.tables is not None
    assert result.tables.table_count == 1
    assert result.tables.page_observations[0].status == "detected"
    assert result.forms is not None
    assert result.forms.page_observations[0].status == "detected"


def test_pdf_digital_reader_rejects_pdf_without_enough_text(tmp_path: Path) -> None:
    class EmptyPdfExtractor:
        def extract_pages(self, source_path: Path) -> list[PdfPage]:
            return [PdfPage(page_number=1, text="", tables=[])]

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    try:
        PdfDigitalReader(extractor=EmptyPdfExtractor()).read(source)
    except RuntimeError as exc:
        assert "PDF text layer insufficient" in str(exc)
    else:
        raise AssertionError("Expected scanned PDF fallback signal")


def test_pdf_scanned_reader_uses_mock_ocr_engine_and_flags_low_confidence(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake scan")
    engine = MockOcrEngine(
        pages=[
            {
                "page_number": 1,
                "text": "Texto OCR",
                "confidence": 0.42,
                "contains_handwriting": True,
            }
        ]
    )

    result = PdfScannedReader(ocr_engine=engine, low_confidence_threshold=0.70).read(source)

    assert result.extraction_method == "ocr"
    assert result.page_count == 1
    assert result.ocr is not None
    assert result.ocr.document_confidence.value == 0.42
    assert result.pages[0].ocr_confidence.value == 0.42
    assert "low_ocr_confidence" in result.review_reasons
    assert "possible_handwriting" in result.review_reasons


def test_pdf_scanned_reader_rejects_boolean_confidence_before_numeric_coercion(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake scan")
    engine = MockOcrEngine(
        pages=[
            {
                "page_number": 1,
                "text": "Texto OCR",
                "confidence": True,
            }
        ]
    )

    result = PdfScannedReader(ocr_engine=engine, low_confidence_threshold=0.70).read(source)

    assert result.pages[0].ocr_confidence.kind == "unavailable"
    assert result.ocr is not None
    assert result.ocr.document_confidence.kind == "unavailable"
    assert "boolean_ocr_confidence_rejected" in result.review_reasons
