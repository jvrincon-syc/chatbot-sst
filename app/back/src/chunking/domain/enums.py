from __future__ import annotations

from enum import StrEnum


class StructuralBlockKind(StrEnum):
    """Supported structural elements supplied by a normalized document."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    FORM = "form"
    NOTE = "note"


class ZeroOverlapReason(StrEnum):
    """Auditable semantic reasons for intentionally omitting overlap."""

    DOCUMENT_START = "document_start"
    SECTION_BOUNDARY = "section_boundary"
    TABLE_OR_FORM_BOUNDARY = "table_or_form_boundary"
