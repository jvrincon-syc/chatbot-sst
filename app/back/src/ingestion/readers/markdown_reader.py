from __future__ import annotations

from pathlib import Path

from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import PageRecord
from ingestion.schemas.common import ConfidenceMetric


class MarkdownReader:
    def read(self, source_path: Path) -> ReadResult:
        text_raw = source_path.read_text(encoding="utf-8")
        text_normalized = normalize_text(text_raw)
        warnings = []
        if not any(line.lstrip().startswith("#") for line in text_normalized.splitlines()):
            warnings.append("missing_title")
        page = PageRecord(
            page_number=1,
            text_raw=text_raw,
            text_normalized=text_normalized,
            extraction_method="markdown",
            ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            warnings=warnings,
        )
        return ReadResult(
            extraction_method="markdown",
            markdown=text_normalized,
            pages=[page],
            warnings=warnings,
            review_reasons=[],
        )
