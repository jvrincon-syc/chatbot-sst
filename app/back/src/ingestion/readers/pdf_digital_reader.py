from __future__ import annotations

from pathlib import Path
from typing import List, Protocol

from pydantic import BaseModel, Field

from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import PageRecord, TableRecord, TablesArtifact


class PdfPage(BaseModel):
    page_number: int
    text: str
    tables: List[TableRecord] = Field(default_factory=list)


class PdfExtractor(Protocol):
    def extract_pages(self, source_path: Path) -> List[PdfPage]:
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
    def __init__(self, extractor: PdfExtractor = None, min_extractable_words: int = 10) -> None:
        self.extractor = extractor or PypdfTextExtractor()
        self.min_extractable_words = min_extractable_words

    def read(self, source_path: Path) -> ReadResult:
        extracted_pages = self.extractor.extract_pages(source_path)
        pages: List[PageRecord] = []
        markdown_parts: List[str] = []
        table_records: List[TableRecord] = []

        for extracted in extracted_pages:
            text_raw = extracted.text
            text_normalized = normalize_text(text_raw)
            markdown_parts.append(f"<!-- page: {extracted.page_number} -->\n\n{text_normalized}")
            pages.append(
                PageRecord(
                    page_number=extracted.page_number,
                    text_raw=text_raw,
                    text_normalized=text_normalized,
                    extraction_method="pdf_digital",
                    warnings=[] if text_normalized else ["partial_extraction"],
                )
            )
            table_records.extend(extracted.tables)

        word_count = sum(len(page.text_normalized.split()) for page in pages)
        if word_count < self.min_extractable_words:
            raise RuntimeError("PDF text layer insufficient; OCR required.")

        tables = None
        if table_records:
            tables = TablesArtifact(document_id="pending", table_count=len(table_records), tables=table_records)

        return ReadResult(
            extraction_method="pdf_digital",
            markdown="\n\n".join(markdown_parts).strip(),
            pages=pages,
            warnings=[],
            review_reasons=[],
            tables=tables,
        )
