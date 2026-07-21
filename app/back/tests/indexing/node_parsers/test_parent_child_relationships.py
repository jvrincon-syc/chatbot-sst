from __future__ import annotations

from llama_index.core import Document
from llama_index.core.schema import NodeRelationship

from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)


def _document() -> Document:
    return Document(
        id_="doc_abc",
        text=(
            "<!-- page: 1 -->\n\n"
            "Primer apartado con obligaciones SST.\n\n"
            "<!-- page: 2 -->\n\n"
            "Segundo apartado con responsabilidades y evidencias."
        ),
        metadata={
            "ref_doc_id": "doc_abc",
            "document_type": "manual",
            "topic": "SST",
            "page_catalog": [
                {"page_number": 1, "char_start": 0, "char_end": 54},
                {"page_number": 2, "char_start": 56, "char_end": 122},
            ],
        },
    )


def test_structure_aware_parser_creates_deterministic_parent_child_nodes() -> None:
    parser = StructureAwareNodeParser(max_child_chars=32)

    nodes = parser.parse(_document())

    parent_nodes = [node for node in nodes if node.metadata["node_role"] == "parent"]
    child_nodes = [node for node in nodes if node.metadata["node_role"] == "child"]
    assert [node.id_ for node in parent_nodes] == [
        "doc_abc:page:1:parent",
        "doc_abc:page:2:parent",
    ]
    assert [node.id_ for node in child_nodes] == [
        "doc_abc:page:1:parent:child:001",
        "doc_abc:page:1:parent:child:002",
        "doc_abc:page:2:parent:child:001",
        "doc_abc:page:2:parent:child:002",
        "doc_abc:page:2:parent:child:003",
    ]


def test_structure_aware_parser_sets_parent_relationship_on_every_child() -> None:
    nodes = StructureAwareNodeParser(max_child_chars=32).parse(_document())
    child_nodes = [node for node in nodes if node.metadata["node_role"] == "child"]

    assert child_nodes
    for node in child_nodes:
        parent = node.relationships[NodeRelationship.PARENT]
        assert parent.node_id == node.metadata["parent_node_id"]
        assert node.metadata["page_number"] in {1, 2}
        assert node.metadata["ref_doc_id"] == "doc_abc"
