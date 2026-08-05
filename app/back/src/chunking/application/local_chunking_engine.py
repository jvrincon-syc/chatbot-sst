from __future__ import annotations

from dataclasses import dataclass, replace

from chunking.application.child_chunk_builder import ChildChunkBuilder
from chunking.application.parent_chunk_builder import ParentChunkBuilder
from chunking.application.ports import StructuralChunkerPort
from chunking.application.structural_parser import StructuralParser
from chunking.domain.models import ChunkBundle, ChunkingProfile, NormalizedDocumentBundle


@dataclass(frozen=True)
class LocalChunkingEngine(StructuralChunkerPort):
    """Single local implementation for deterministic structural chunking."""

    structural_parser: StructuralParser = StructuralParser()
    parent_builder: ParentChunkBuilder = ParentChunkBuilder()
    child_builder: ChildChunkBuilder = ChildChunkBuilder()

    def chunk(
        self,
        document: NormalizedDocumentBundle,
        profile: ChunkingProfile,
    ) -> ChunkBundle:
        blocks = self.structural_parser.parse(document)
        enriched_document = replace(document, structural_blocks=blocks)
        parents = self.parent_builder.build(
            document_id=document.document_id,
            profile=profile,
            blocks=blocks,
        )
        block_by_id = {block.block_id: block for block in blocks}
        children = []
        for parent in parents:
            parent_blocks = tuple(block_by_id[block_id] for block_id in parent.block_ids)
            children.extend(
                self.child_builder.build(
                    parent=parent,
                    blocks=parent_blocks,
                    profile=profile,
                )
            )
        bundle = ChunkBundle(
            document_id=document.document_id,
            profile=profile,
            parents=tuple(parents),
            children=tuple(children),
        )
        bundle.validate_against_document(enriched_document)
        return bundle
