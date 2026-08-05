from __future__ import annotations

from collections.abc import Sequence

from llama_index.core.schema import BaseNode


class InMemoryDocStore:
    def __init__(self) -> None:
        self._nodes: dict[str, BaseNode] = {}

    def snapshot(self) -> dict[str, BaseNode]:
        return dict(self._nodes)

    def restore(self, snapshot: dict[str, BaseNode]) -> None:
        self._nodes = dict(snapshot)

    def upsert_nodes(self, nodes: Sequence[BaseNode]) -> None:
        for node in nodes:
            self._nodes[node.id_] = node

    def delete_by_ref_doc_id(self, ref_doc_id: str) -> int:
        deleted = [
            node_id
            for node_id, node in self._nodes.items()
            if node.metadata.get("ref_doc_id") == ref_doc_id
        ]
        for node_id in deleted:
            del self._nodes[node_id]
        return len(deleted)

    def nodes_for_ref_doc_id(self, ref_doc_id: str) -> list[BaseNode]:
        return [
            node
            for node in self._nodes.values()
            if node.metadata.get("ref_doc_id") == ref_doc_id
        ]
