from __future__ import annotations

from pathlib import Path

from ingestion.ocr.mock_engine import MockOcrEngine
from ingestion.readers.markdown_reader import MarkdownReader
from ingestion.readers.pdf_digital_reader import PdfDigitalReader, PdfPage
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
    assert result.ocr.overall_confidence == 0.42
    assert "low_ocr_confidence" in result.review_reasons
    assert "possible_handwriting" in result.review_reasons
