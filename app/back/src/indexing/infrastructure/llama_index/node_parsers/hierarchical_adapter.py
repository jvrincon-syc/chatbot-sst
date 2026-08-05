from __future__ import annotations

from llama_index.core import Document
from llama_index.core.node_parser import HierarchicalNodeParser
from llama_index.core.schema import BaseNode


class HierarchicalNodeParserAdapter:
    def __init__(self, *, chunk_sizes: list[int] | None = None) -> None:
        self._parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=chunk_sizes or [2048, 512, 128],
            chunk_overlap=20,
        )

    def parse(self, document: Document) -> list[BaseNode]:
        return list(self._parser.get_nodes_from_documents([document]))
