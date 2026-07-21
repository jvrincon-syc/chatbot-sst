from __future__ import annotations

from retrieval.fusion import RetrievedCandidate
from retrieval.parent_expansion import ParentExpansionService


def test_parent_expansion_returns_parent_with_leaf_evidence() -> None:
    service = ParentExpansionService(
        parents={
            "p1": RetrievedCandidate("p1", "parent text", 0.0, "docstore", {}),
        }
    )
    leaf = RetrievedCandidate(
        "c1",
        "leaf text",
        0.8,
        "vector",
        {"parent_node_id": "p1", "page_number": 2},
    )

    expanded = service.expand([leaf])

    assert expanded[0].node_id == "p1"
    assert expanded[0].metadata["evidence_leaf_id"] == "c1"
    assert expanded[0].metadata["page_number"] == 2
