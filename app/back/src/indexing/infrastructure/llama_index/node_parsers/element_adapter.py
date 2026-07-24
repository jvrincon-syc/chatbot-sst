from __future__ import annotations

from llama_index.core import Document
from llama_index.core.schema import TextNode

from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)


class ElementAwareNodeParserAdapter:
    """Element-aware facade that now delegates to the bundle adapter."""

    def __init__(self) -> None:
        self._parser = StructureAwareNodeParser()

    def parse(self, document: Document) -> list[TextNode]:
        return self._parser.parse(document)
