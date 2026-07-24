from __future__ import annotations

import logging
import re

from chunking.domain.enums import StructuralBlockKind
from chunking.domain.models import NormalizedDocumentBundle, SourceSpan, StructuralBlock
from chunking.infrastructure.markdown_adapter import MarkdownAdapter, MarkdownRegion


logger = logging.getLogger(__name__)
_FORM_LABEL_RE = re.compile(r"^\*{0,2}[A-ZÁÉÍÓÚÑ][^:\n]{0,80}:\*{0,2}$", re.MULTILINE)


class StructuralParser:
    """Builds semantic structural blocks from normalized markdown plus sidecars."""

    def __init__(self, markdown_adapter: MarkdownAdapter | None = None) -> None:
        self._markdown_adapter = markdown_adapter or MarkdownAdapter()

    def parse(self, bundle: NormalizedDocumentBundle) -> tuple[StructuralBlock, ...]:
        regions = self._markdown_adapter.extract(bundle.markdown)
        repeated_heading_counts = self._heading_counts(regions)
        heading_path: list[str] = []
        blocks: list[StructuralBlock] = []

        logger.info(
            "Parsing structural markdown",
            extra={
                "document_id": bundle.document_id,
                "region_count": len(regions),
                "forms_present": bundle.sidecars.forms_present,
                "tables_present": bundle.sidecars.tables_present,
            },
        )

        for ordinal, region in enumerate(regions):
            if region.kind == "heading":
                if self._is_non_semantic_heading(bundle, region, repeated_heading_counts):
                    kind = StructuralBlockKind.NOTE
                    block_heading_path = ()
                else:
                    kind = StructuralBlockKind.HEADING
                    self._apply_heading_path(heading_path, region)
                    block_heading_path = tuple(heading_path)
                blocks.append(self._block_from_region(bundle, ordinal, region, kind, block_heading_path))
                continue

            if region.kind == "table":
                kind = StructuralBlockKind.TABLE
            elif region.kind == "list":
                kind = StructuralBlockKind.LIST
            elif self._is_form_region(region, bundle):
                kind = StructuralBlockKind.FORM
            else:
                kind = StructuralBlockKind.PARAGRAPH

            blocks.append(
                self._block_from_region(
                    bundle,
                    ordinal,
                    region,
                    kind,
                    tuple(heading_path),
                )
            )

        logger.info(
            "Parsed structural blocks",
            extra={
                "document_id": bundle.document_id,
                "block_count": len(blocks),
            },
        )
        return tuple(blocks)

    def _block_from_region(
        self,
        bundle: NormalizedDocumentBundle,
        ordinal: int,
        region: MarkdownRegion,
        kind: StructuralBlockKind,
        heading_path: tuple[str, ...],
    ) -> StructuralBlock:
        return StructuralBlock.create(
            document_id=bundle.document_id,
            ordinal=ordinal,
            kind=kind,
            text=region.text,
            source_span=self._source_span(bundle, region),
            heading_path=heading_path,
        )

    def _source_span(self, bundle: NormalizedDocumentBundle, region: MarkdownRegion) -> SourceSpan:
        overlapping_pages = [
            trace.page_number
            for trace in bundle.page_traces
            if trace.char_end > region.char_start and trace.char_start < region.char_end
        ]
        if not overlapping_pages:
            raise ValueError("PAGE_TRACE_UNRESOLVED: structural region is outside resolved page traces")
        return SourceSpan(
            page_start=min(overlapping_pages),
            page_end=max(overlapping_pages),
            char_start=region.char_start,
            char_end=region.char_end,
        )

    def _heading_counts(self, regions: tuple[MarkdownRegion, ...]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for region in regions:
            if region.kind != "heading":
                continue
            key = self._normalize_heading(region.text)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _is_non_semantic_heading(
        self,
        bundle: NormalizedDocumentBundle,
        region: MarkdownRegion,
        repeated_heading_counts: dict[str, int],
    ) -> bool:
        normalized = self._normalize_heading(region.text)
        repeated = repeated_heading_counts.get(normalized, 0) > 1
        compact = re.sub(r"\W+", "", region.text, flags=re.UNICODE)
        mostly_upper = compact.isupper() if compact else False
        near_page_start = any(
            region.char_start - trace.char_start <= 20
            for trace in bundle.page_traces
            if 0 <= region.char_start - trace.char_start <= 20
        )
        return repeated and near_page_start and (len(normalized) <= 16 or mostly_upper)

    def _apply_heading_path(self, heading_path: list[str], region: MarkdownRegion) -> None:
        level = region.heading_level or 1
        while len(heading_path) >= level:
            heading_path.pop()
        heading_path.append(region.text)

    def _is_form_region(
        self,
        region: MarkdownRegion,
        bundle: NormalizedDocumentBundle,
    ) -> bool:
        if not bundle.sidecars.forms_present:
            return False
        if any(title and title.lower() in region.text.lower() for title in bundle.sidecars.form_titles):
            return True
        label_matches = _FORM_LABEL_RE.findall(region.text)
        has_form_cues = "____" in region.text or "[ ]" in region.text or "( )" in region.text
        return len(label_matches) >= 2 or has_form_cues

    def _normalize_heading(self, value: str) -> str:
        return " ".join(value.casefold().split())
