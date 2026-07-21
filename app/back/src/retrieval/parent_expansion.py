from __future__ import annotations

from retrieval.fusion import RetrievedCandidate


class ParentExpansionService:
    def __init__(self, *, parents: dict[str, RetrievedCandidate]) -> None:
        self._parents = parents

    def expand(self, leaves: list[RetrievedCandidate]) -> list[RetrievedCandidate]:
        expanded: list[RetrievedCandidate] = []
        for leaf in leaves:
            parent_id = leaf.metadata.get("parent_node_id")
            if not parent_id:
                continue
            parent = self._parents.get(parent_id)
            if parent is None:
                continue
            expanded.append(
                RetrievedCandidate(
                    node_id=parent.node_id,
                    text=parent.text,
                    score=leaf.score,
                    source=leaf.source,
                    metadata={
                        **parent.metadata,
                        **{
                            key: value
                            for key, value in leaf.metadata.items()
                            if key in {"page_number", "retrieval_sources"}
                        },
                        "evidence_leaf_id": leaf.node_id,
                    },
                )
            )
        return expanded
