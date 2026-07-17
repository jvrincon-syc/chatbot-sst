from __future__ import annotations

from pathlib import Path
from typing import Any, List, Protocol

from pydantic import BaseModel, Field

from ingestion.layout.boilerplate import build_indexable_text, detect_boilerplate
from ingestion.layout.pdfplumber_extractor import LayoutCapabilityUnavailableError, PdfLayoutExtractor
from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import PageRecord
from ingestion.schemas.common import ConfidenceMetric, PageBlock
from ingestion.structure.forms import FormExtractor
from ingestion.structure.tables import TableExtractor


class PdfPage(BaseModel):
    page_number: int
    text: str
    blocks: List[PageBlock] = Field(default_factory=list)
    tables: List[Any] = Field(default_factory=list)


class PdfExtractor(Protocol):
    def extract_pages(self, source_path: Path) -> List[Any]:
        ...


class MissingPdfExtractor:
    def extract_pages(self, source_path: Path) -> List[PdfPage]:
        raise RuntimeError("No PDF extractor configured. Install PyMuPDF/pypdf or inject an extractor.")


class PypdfTextExtractor:
    def extract_pages(self, source_path: Path) -> List[PdfPage]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(source_path))
            return [
                PdfPage(page_number=index, text=page.extract_text() or "", tables=[])
                for index, page in enumerate(reader.pages, start=1)
            ]
        except Exception as exc:
            raise RuntimeError(f"PDF text extraction failed: {exc}") from exc


class PdfDigitalReader:
    def __init__(
        self,
        extractor: PdfExtractor = None,
        min_extractable_words: int = 10,
        table_extractor: TableExtractor | None = None,
        form_extractor: FormExtractor | None = None,
    ) -> None:
        self.extractor = extractor or PdfLayoutExtractor()
        self.min_extractable_words = min_extractable_words
        self.table_extractor = table_extractor or TableExtractor()
        self.form_extractor = form_extractor or FormExtractor()

    def read(self, source_path: Path) -> ReadResult:
        layout_capable = True
        try:
            extracted_pages = self.extractor.extract_pages(source_path)
        except LayoutCapabilityUnavailableError:
            extracted_pages = PypdfTextExtractor().extract_pages(source_path)
            layout_capable = False

        digital_pages = [_coerce_page(extracted) for extracted in extracted_pages]
        boilerplate = detect_boilerplate(digital_pages) if any(page.blocks for page in digital_pages) else None
        pages: List[PageRecord] = []
        markdown_parts: List[str] = []

        for extracted in digital_pages:
            text_raw = extracted.text
            removed_spans = boilerplate.removed_spans_for_page(extracted.page_number) if boilerplate else []
            text_normalized = build_indexable_text(extracted, boilerplate) if boilerplate else normalize_text(text_raw)
            markdown_parts.append(f"<!-- page: {extracted.page_number} -->\n\n{text_normalized}")
            pages.append(
                PageRecord(
                    page_number=extracted.page_number,
                    text_raw=text_raw,
                    text_normalized=text_normalized,
                    extraction_method="pdf_digital",
                    blocks=extracted.blocks,
                    removed_spans=removed_spans,
                    ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
                    warnings=[] if text_normalized else ["partial_extraction"],
                )
            )
        word_count = sum(len(page.text_normalized.split()) for page in pages)
        if word_count < self.min_extractable_words:
            raise RuntimeError("PDF text layer insufficient; OCR required.")

        tables = (
            self.table_extractor
            if layout_capable
            else TableExtractor(backend_available=False)
        ).evaluate_pages(digital_pages)
        forms = (
            self.form_extractor
            if layout_capable
            else FormExtractor(backend_available=False)
        ).evaluate_pages(digital_pages)

        return ReadResult(
            extraction_method="pdf_digital",
            markdown="\n\n".join(markdown_parts).strip(),
            pages=pages,
            warnings=[],
            review_reasons=[],
            tables=tables,
            forms=forms,
        )


def _coerce_page(extracted: Any) -> PdfPage:
    if isinstance(extracted, PdfPage):
        return extracted
    page_number = int(getattr(extracted, "page_number"))
    text = str(
        getattr(
            extracted,
            "text",
            getattr(extracted, "text_raw", ""),
        )
        or ""
    )
    layout_blocks = list(getattr(extracted, "blocks", []) or [])
    blocks = [_coerce_block(page_number, block) for block in layout_blocks]
    if not text and blocks:
        text = "\n".join(block.text for block in blocks if block.text)
    tables = list(getattr(extracted, "tables", []) or [])
    return PdfPage(page_number=page_number, text=text, tables=tables, blocks=blocks)


def _coerce_block(page_number: int, block: Any) -> PageBlock:
    if isinstance(block, PageBlock):
        return block
    block_type = str(getattr(block, "block_type", "") or "")
    return PageBlock(
        block_id=str(getattr(block, "block_id", f"p{page_number}_block_{id(block)}")),
        text=str(getattr(block, "text", "") or ""),
        bbox=getattr(block, "bbox", None),
        extraction_method="pdf_digital",
        role="body" if block_type == "text" else block_type or None,
        warnings=list(getattr(block, "warnings", []) or []),
    )
