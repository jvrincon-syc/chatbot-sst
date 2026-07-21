from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llama_index.core import Document
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode


@dataclass(frozen=True)
class StructureAwareNodeParser:
    max_child_chars: int = 900

    def parse(self, document: Document) -> list[TextNode]:
        nodes: list[TextNode] = []
        for page in document.metadata.get("page_catalog", []):
            page_number = int(page["page_number"])
            char_start = int(page["char_start"])
            char_end = int(page["char_end"])
            parent = self._parent_node(
                document=document,
                page_number=page_number,
                char_start=char_start,
                char_end=char_end,
            )
            children = self._child_nodes(parent=parent, document=document)
            parent.relationships[NodeRelationship.CHILD] = [
                RelatedNodeInfo(node_id=child.id_) for child in children
            ]
            nodes.append(parent)
            nodes.extend(children)
        return nodes

    def _parent_node(
        self,
        *,
        document: Document,
        page_number: int,
        char_start: int,
        char_end: int,
    ) -> TextNode:
        parent_id = f"{document.id_}:page:{page_number}:parent"
        text = document.text[char_start:char_end].strip()
        return TextNode(
            id_=parent_id,
            text=text,
            metadata={
                **self._base_metadata(document),
                "node_role": "parent",
                "page_number": page_number,
                "parent_node_id": None,
                "char_start": char_start,
                "char_end": char_end,
            },
            start_char_idx=char_start,
            end_char_idx=char_end,
            excluded_embed_metadata_keys=list(document.excluded_embed_metadata_keys),
        )

    def _child_nodes(self, *, parent: TextNode, document: Document) -> list[TextNode]:
        chunks = _split_text(parent.text, self.max_child_chars)
        children: list[TextNode] = []
        cursor = parent.start_char_idx or 0
        for index, chunk in enumerate(chunks, start=1):
            child_start = document.text.find(chunk, cursor)
            if child_start < 0:
                child_start = cursor
            child_end = child_start + len(chunk)
            child = TextNode(
                id_=f"{parent.id_}:child:{index:03d}",
                text=chunk,
                metadata={
                    **self._base_metadata(document),
                    "node_role": "child",
                    "page_number": parent.metadata["page_number"],
                    "parent_node_id": parent.id_,
                    "char_start": child_start,
                    "char_end": child_end,
                },
                relationships={
                    NodeRelationship.PARENT: RelatedNodeInfo(node_id=parent.id_)
                },
                start_char_idx=child_start,
                end_char_idx=child_end,
                excluded_embed_metadata_keys=list(document.excluded_embed_metadata_keys),
            )
            children.append(child)
            cursor = child_end
        return children

    def _base_metadata(self, document: Document) -> dict[str, Any]:
        return {
            key: value
            for key, value in document.metadata.items()
            if key != "page_catalog"
        }


def _split_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_child_chars must be positive")
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = word
    chunks.append(current)
    return chunks
