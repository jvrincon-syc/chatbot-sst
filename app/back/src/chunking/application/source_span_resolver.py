from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from chunking.domain.models import PageTrace
from ingestion.schemas.artifacts import PageRecord


PAGE_TRACE_UNRESOLVED = "PAGE_TRACE_UNRESOLVED"
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


@dataclass(frozen=True)
class PageTraceResolution:
    """Resolved page traces or a fail-closed provenance warning."""

    page_traces: tuple[PageTrace, ...] = ()
    warnings: tuple[str, ...] = ()


class SourceSpanResolver:
    """Resolve Markdown character ranges to source pages without guessing."""

    def resolve(self, *, markdown: str, pages: Sequence[PageRecord]) -> PageTraceResolution:
        """Prefer explicit page markers, then require unique sequential text alignment."""
        source_page_numbers = tuple(page.page_number for page in pages)
        if len(source_page_numbers) != len(set(source_page_numbers)):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))
        marker_resolution = self._resolve_markers(markdown=markdown, pages=pages)
        if marker_resolution is not None:
            return marker_resolution

        aligned_traces = self._resolve_alignment(markdown=markdown, pages=pages)
        if aligned_traces is not None:
            return PageTraceResolution(page_traces=aligned_traces)

        return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))

    def _resolve_markers(
        self, *, markdown: str, pages: Sequence[PageRecord]
    ) -> PageTraceResolution | None:
        matches = tuple(_PAGE_MARKER_RE.finditer(markdown))
        if not matches:
            return None
        page_numbers = tuple(int(match.group(1)) for match in matches)
        if len(page_numbers) != len(set(page_numbers)):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))
        if page_numbers != tuple(sorted(page_numbers)):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))

        page_by_number = {page.page_number: page for page in pages}
        if any(page_number not in page_by_number for page_number in page_numbers):
            return PageTraceResolution(warnings=(PAGE_TRACE_UNRESOLVED,))
        traces: list[PageTrace] = []
        for index, match in enumerate(matches):
            page_number = page_numbers[index]
            page = page_by_number[page_number]
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            traces.append(
                PageTrace(
                    page_number=page_number,
                    char_start=match.start(),
                    char_end=next_start,
                    text_raw=getattr(page, "text_raw", page.text_normalized),
                    text_normalized=page.text_normalized,
                )
            )
        return PageTraceResolution(page_traces=tuple(traces))

    def _resolve_alignment(
        self, *, markdown: str, pages: Sequence[PageRecord]
    ) -> tuple[PageTrace, ...] | None:
        if not pages:
            return None
        traces: list[PageTrace] = []
        search_start = 0
        for page in pages:
            text = page.text_normalized
            if not text:
                return None
            position = markdown.find(text, search_start)
            if position < 0 or markdown.find(text, position + 1) >= 0:
                return None
            end = position + len(text)
            traces.append(
                PageTrace(
                    page_number=page.page_number,
                    char_start=position,
                    char_end=end,
                    text_raw=getattr(page, "text_raw", page.text_normalized),
                    text_normalized=page.text_normalized,
                )
            )
            search_start = end
        return tuple(traces)
