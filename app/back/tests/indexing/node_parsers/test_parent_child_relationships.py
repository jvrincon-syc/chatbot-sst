from __future__ import annotations

from llama_index.core import Document
from llama_index.core.schema import NodeRelationship

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.models import (
    ChunkBundle,
    ChunkingProfile,
    ChildChunk,
    ParentChunk,
    SourceSpan,
)
from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)


def _bundle() -> ChunkBundle:
    profile = ChunkingProfile.local_structural_v1()
    parent_text = (
        "Primer apartado con obligaciones SST.\n\n"
        "Segundo apartado con responsabilidades y evidencias."
    )
    child_text = "Primer apartado con obligaciones SST."
    parent = ParentChunk.create(
        document_id="doc_abc",
        profile_id=profile.profile_id,
        ordinal=0,
        text=parent_text,
        source_span=SourceSpan(
            page_start=1,
            page_end=2,
            char_start=0,
            char_end=len(parent_text),
        ),
        block_ids=("block-1", "block-2"),
    )
    child = ChildChunk.create(
        document_id="doc_abc",
        profile_id=profile.profile_id,
        parent_id=parent.chunk_id,
        ordinal=0,
        text=child_text,
        source_span=SourceSpan(
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=len(child_text),
        ),
        token_start=0,
        token_end=4,
        token_count=4,
        overlap_previous_tokens=0,
        overlap_next_tokens=0,
        context_prefix="Contexto previo",
        zero_overlap_reasons=frozenset({ZeroOverlapReason.DOCUMENT_START}),
    )
    return ChunkBundle(
        document_id="doc_abc",
        profile=profile,
        parents=(parent,),
        children=(child,),
    )


def _document() -> Document:
    bundle = _bundle()
    return Document(
        id_="doc_abc",
        text=bundle.parents[0].text,
        metadata={
            "ref_doc_id": "doc_abc",
            "document_id": "doc_abc",
            "document_type": "manual",
            "topic": "SST",
            "source_relpath": "manual/doc.pdf",
            "source_hash": "a" * 64,
            "normalized_relpath": "manual/doc.md",
            "corpus_version": "phase1",
            "processing_fingerprint": "fingerprint-1",
            "chunking_version": "structure-aware-v1",
            "chunking_bundle": bundle,
        },
    )


def test_structure_aware_parser_creates_deterministic_parent_child_nodes() -> None:
    nodes = StructureAwareNodeParser().parse(_document())

    parent_nodes = [node for node in nodes if node.metadata["node_role"] == "parent"]
    child_nodes = [node for node in nodes if node.metadata["node_role"] == "child"]
    assert len(parent_nodes) == 1
    assert len(child_nodes) == 1
    assert parent_nodes[0].id_ == _bundle().parents[0].chunk_id
    assert child_nodes[0].id_ == _bundle().children[0].chunk_id
    assert child_nodes[0].metadata["parent_node_id"] == parent_nodes[0].id_
    assert child_nodes[0].text == _bundle().children[0].text


def test_structure_aware_parser_sets_parent_relationship_on_every_child() -> None:
    nodes = StructureAwareNodeParser().parse(_document())
    child_nodes = [node for node in nodes if node.metadata["node_role"] == "child"]

    assert child_nodes
    for node in child_nodes:
        parent = node.relationships[NodeRelationship.PARENT]
        assert parent.node_id == node.metadata["parent_node_id"]
        assert node.metadata["page_start"] == 1
        assert node.metadata["page_end"] == 1
        assert node.metadata["ref_doc_id"] == "doc_abc"


def test_structure_aware_parser_preserves_parent_spans_and_text() -> None:
    nodes = StructureAwareNodeParser().parse(_document())

    parent_nodes = [node for node in nodes if node.metadata["node_role"] == "parent"]

    assert len(parent_nodes) == 1
    assert parent_nodes[0].metadata["page_start"] == 1
    assert parent_nodes[0].metadata["page_end"] == 2
    assert "Segundo apartado" in parent_nodes[0].text


def test_structure_aware_parser_exposes_overlap_only_through_metadata() -> None:
    nodes = StructureAwareNodeParser().parse(_document())
    child_nodes = [node for node in nodes if node.metadata["node_role"] == "child"]

    assert len(child_nodes) == 1
    assert child_nodes[0].metadata["overlap_previous_tokens"] == 0
    assert child_nodes[0].metadata["overlap_next_tokens"] == 0
    assert child_nodes[0].metadata["context_prefix"] == "Contexto previo"
