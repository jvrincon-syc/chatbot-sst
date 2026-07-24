from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chunking.domain.models import ChunkBundle, ChildChunk, ParentChunk
from llama_index.core import Document
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode


@dataclass(frozen=True)
class StructureAwareNodeParser:
    """Adapt a validated chunk bundle into LlamaIndex nodes without rechunking."""

    def parse(self, document: Document) -> list[TextNode]:
        bundle = document.metadata.get("chunking_bundle")
        if not isinstance(bundle, ChunkBundle):
            raise ValueError("chunking_bundle metadata is required for node adaptation")
        if bundle.document_id != document.id_ and bundle.document_id != document.metadata.get(
            "ref_doc_id"
        ):
            raise ValueError("chunking_bundle document_id must match the document")

        nodes: list[TextNode] = []
        children_by_parent: dict[str, list[TextNode]] = {}
        for child_chunk in bundle.children:
            child_node = self._child_node(
                document=document,
                bundle=bundle,
                child_chunk=child_chunk,
            )
            children_by_parent.setdefault(child_chunk.parent_id, []).append(child_node)

        for parent_chunk in bundle.parents:
            parent_node = self._parent_node(
                document=document,
                bundle=bundle,
                parent_chunk=parent_chunk,
            )
            children = children_by_parent.get(parent_chunk.chunk_id, [])
            parent_node.relationships[NodeRelationship.CHILD] = [
                RelatedNodeInfo(node_id=child.id_) for child in children
            ]
            nodes.append(parent_node)
            nodes.extend(children)

        return nodes

    def _parent_node(
        self,
        *,
        document: Document,
        bundle: ChunkBundle,
        parent_chunk: ParentChunk,
    ) -> TextNode:
        metadata = {
            **self._base_metadata(document),
            "node_role": "parent",
            "parent_node_id": None,
            "parent_chunk_id": parent_chunk.chunk_id,
            "chunk_index": parent_chunk.ordinal,
            "chunking_profile_id": bundle.profile.profile_id,
            "page_start": parent_chunk.source_span.page_start,
            "page_end": parent_chunk.source_span.page_end,
            "char_start": parent_chunk.source_span.char_start,
            "char_end": parent_chunk.source_span.char_end,
            "source_span": parent_chunk.source_span.as_payload(),
            "block_ids": list(parent_chunk.block_ids),
        }
        return TextNode(
            id_=parent_chunk.chunk_id,
            text=parent_chunk.text,
            metadata=metadata,
            start_char_idx=parent_chunk.source_span.char_start,
            end_char_idx=parent_chunk.source_span.char_end,
            excluded_embed_metadata_keys=list(document.excluded_embed_metadata_keys),
        )

    def _child_node(
        self,
        *,
        document: Document,
        bundle: ChunkBundle,
        child_chunk: ChildChunk,
    ) -> TextNode:
        metadata = {
            **self._base_metadata(document),
            "node_role": "child",
            "parent_node_id": child_chunk.parent_id,
            "parent_chunk_id": child_chunk.parent_id,
            "child_chunk_id": child_chunk.chunk_id,
            "chunk_index": child_chunk.chunk_index,
            "chunking_profile_id": bundle.profile.profile_id,
            "page_start": child_chunk.source_span.page_start,
            "page_end": child_chunk.source_span.page_end,
            "char_start": child_chunk.source_span.char_start,
            "char_end": child_chunk.source_span.char_end,
            "source_span": child_chunk.source_span.as_payload(),
            "token_start": child_chunk.token_start,
            "token_end": child_chunk.token_end,
            "token_count": child_chunk.token_count,
            "overlap_previous_tokens": child_chunk.overlap_previous_tokens,
            "overlap_next_tokens": child_chunk.overlap_next_tokens,
            "overlap_previous_span": (
                child_chunk.overlap_previous_span.as_payload()
                if child_chunk.overlap_previous_span is not None
                else None
            ),
            "overlap_next_span": (
                child_chunk.overlap_next_span.as_payload()
                if child_chunk.overlap_next_span is not None
                else None
            ),
            "context_prefix": child_chunk.context_prefix,
            "zero_overlap_reasons": sorted(
                reason.value for reason in child_chunk.zero_overlap_reasons
            ),
            "warnings": list(child_chunk.warnings),
        }
        return TextNode(
            id_=child_chunk.chunk_id,
            text=child_chunk.text,
            metadata=metadata,
            relationships={
                NodeRelationship.PARENT: RelatedNodeInfo(node_id=child_chunk.parent_id)
            },
            start_char_idx=child_chunk.source_span.char_start,
            end_char_idx=child_chunk.source_span.char_end,
            excluded_embed_metadata_keys=list(document.excluded_embed_metadata_keys),
        )

    def _base_metadata(self, document: Document) -> dict[str, Any]:
        return {
            key: value
            for key, value in document.metadata.items()
            if key not in {"chunking_bundle", "page_catalog"}
        }
