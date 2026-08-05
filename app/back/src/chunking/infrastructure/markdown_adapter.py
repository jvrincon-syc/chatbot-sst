from __future__ import annotations

from dataclasses import dataclass
import re


_FRONT_MATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*\d+\s*-->\s*(?:\r?\n)?")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<text>.+?)\s*$")
_ARTICLE_RE = re.compile(r"^(?P<label>(?:art[ií]culo\s+\d+|(?:\d+\.)+\d*|\d+\.\d+|\d+\.))\s*(?P<text>.+)?$", re.IGNORECASE)
_LIST_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+).+")


@dataclass(frozen=True)
class MarkdownRegion:
    """A contiguous content region with original markdown coordinates."""

    kind: str
    text: str
    char_start: int
    char_end: int
    heading_level: int | None = None


class MarkdownAdapter:
    """Extracts structural markdown regions without turning pages into boundaries."""

    def extract(self, markdown: str) -> tuple[MarkdownRegion, ...]:
        cursor = self._body_start(markdown)
        regions: list[MarkdownRegion] = []
        while cursor < len(markdown):
            cursor = self._skip_blanks_and_markers(markdown, cursor)
            if cursor >= len(markdown):
                break

            table_region = self._consume_html_table(markdown, cursor)
            if table_region is not None:
                regions.append(table_region)
                cursor = table_region.char_end
                continue

            line, line_end, next_cursor = _read_line(markdown, cursor)
            stripped = line.strip()
            heading_match = _HEADING_RE.match(stripped)
            if heading_match is not None:
                regions.append(
                    MarkdownRegion(
                        kind="heading",
                        text=heading_match.group("text").strip(),
                        char_start=cursor,
                        char_end=line_end,
                        heading_level=len(heading_match.group(1)),
                    )
                )
                cursor = next_cursor
                continue

            if _LIST_RE.match(stripped):
                list_region = self._consume_list(markdown, cursor)
                regions.append(list_region)
                cursor = list_region.char_end
                continue

            article_match = _ARTICLE_RE.match(stripped)
            if article_match is not None and self._looks_like_article_heading(article_match.group("label")):
                regions.append(
                    MarkdownRegion(
                        kind="heading",
                        text=stripped,
                        char_start=cursor,
                        char_end=line_end,
                        heading_level=self._article_level(article_match.group("label")),
                    )
                )
                cursor = next_cursor
                continue

            if stripped.startswith("|"):
                table_region = self._consume_pipe_table(markdown, cursor)
                regions.append(table_region)
                cursor = table_region.char_end
                continue

            paragraph_region = self._consume_paragraph(markdown, cursor)
            regions.append(paragraph_region)
            cursor = paragraph_region.char_end
        return tuple(regions)

    def _body_start(self, markdown: str) -> int:
        match = _FRONT_MATTER_RE.match(markdown)
        return match.end() if match is not None else 0

    def _skip_blanks_and_markers(self, markdown: str, cursor: int) -> int:
        while cursor < len(markdown):
            marker_match = _PAGE_MARKER_RE.match(markdown, cursor)
            if marker_match is not None:
                cursor = marker_match.end()
                continue
            line, _line_end, next_cursor = _read_line(markdown, cursor)
            if line.strip():
                break
            cursor = next_cursor
        return cursor

    def _consume_html_table(self, markdown: str, cursor: int) -> MarkdownRegion | None:
        if not markdown[cursor:].lstrip().startswith("<table"):
            return None
        leading_spaces = len(markdown[cursor:]) - len(markdown[cursor:].lstrip())
        start = cursor + leading_spaces
        end = markdown.find("</table>", start)
        if end < 0:
            return None
        end += len("</table>")
        return MarkdownRegion(
            kind="table",
            text=markdown[start:end].strip(),
            char_start=start,
            char_end=end,
        )

    def _consume_pipe_table(self, markdown: str, cursor: int) -> MarkdownRegion:
        lines: list[str] = []
        start = cursor
        end = cursor
        current = cursor
        while current < len(markdown):
            marker_match = _PAGE_MARKER_RE.match(markdown, current)
            if marker_match is not None:
                current = marker_match.end()
                continue
            line, line_end, next_cursor = _read_line(markdown, current)
            if not line.strip():
                break
            if not line.strip().startswith("|"):
                break
            lines.append(line.strip())
            end = line_end
            current = next_cursor
        return MarkdownRegion(
            kind="table",
            text="\n".join(lines),
            char_start=start,
            char_end=end,
        )

    def _consume_list(self, markdown: str, cursor: int) -> MarkdownRegion:
        lines: list[str] = []
        start = cursor
        end = cursor
        current = cursor
        while current < len(markdown):
            marker_match = _PAGE_MARKER_RE.match(markdown, current)
            if marker_match is not None:
                current = marker_match.end()
                continue
            line, line_end, next_cursor = _read_line(markdown, current)
            if not line.strip():
                break
            if not _LIST_RE.match(line.strip()):
                break
            lines.append(line.strip())
            end = line_end
            current = next_cursor
        return MarkdownRegion(
            kind="list",
            text="\n".join(lines),
            char_start=start,
            char_end=end,
        )

    def _consume_paragraph(self, markdown: str, cursor: int) -> MarkdownRegion:
        lines: list[str] = []
        start = cursor
        end = cursor
        current = cursor
        while current < len(markdown):
            marker_match = _PAGE_MARKER_RE.match(markdown, current)
            if marker_match is not None:
                current = marker_match.end()
                continue
            line, line_end, next_cursor = _read_line(markdown, current)
            stripped = line.strip()
            if not stripped:
                break
            if current != cursor and (
                stripped.startswith("<table")
                or stripped.startswith("|")
                or _LIST_RE.match(stripped)
                or _HEADING_RE.match(stripped)
                or (
                    (article_match := _ARTICLE_RE.match(stripped)) is not None
                    and self._looks_like_article_heading(article_match.group("label"))
                )
            ):
                break
            lines.append(stripped)
            end = line_end
            current = next_cursor
        return MarkdownRegion(
            kind="paragraph",
            text="\n".join(lines),
            char_start=start,
            char_end=end,
        )

    def _looks_like_article_heading(self, label: str) -> bool:
        lowered = label.lower()
        dotted_numeric = re.fullmatch(r"\d+\.\d+(?:\.\d+)*", label.rstrip(".")) is not None
        return lowered.startswith("articulo") or lowered.startswith("artículo") or dotted_numeric

    def _article_level(self, label: str) -> int:
        dotted = label.strip().rstrip(".")
        if dotted.lower().startswith("articulo") or dotted.lower().startswith("artículo"):
            return 1
        return min(6, dotted.count(".") + 1)


def _read_line(markdown: str, cursor: int) -> tuple[str, int, int]:
    newline = markdown.find("\n", cursor)
    if newline < 0:
        return markdown[cursor:], len(markdown), len(markdown)
    line_end = newline
    if line_end > cursor and markdown[line_end - 1] == "\r":
        line_end -= 1
    return markdown[cursor:line_end], line_end, newline + 1
