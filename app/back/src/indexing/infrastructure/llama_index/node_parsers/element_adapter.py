from __future__ import annotations

from llama_index.core import Document
from llama_index.core.schema import TextNode

from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)


class ElementAwareNodeParserAdapter:
    """Element-aware facade for Parse item boundaries.

    The current normalized artifacts expose page boundaries reliably. A later
    benchmark can replace this facade with item/table boundaries without
    changing the application use case.
    """

    def __init__(self, *, max_child_chars: int = 900) -> None:
        self._parser = StructureAwareNodeParser(max_child_chars=max_child_chars)

    def parse(self, document: Document) -> list[TextNode]:
        return self._parser.parse(document)
