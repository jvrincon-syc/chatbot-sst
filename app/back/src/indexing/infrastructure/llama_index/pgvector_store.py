from __future__ import annotations

from collections.abc import Sequence

from llama_index.core.schema import BaseNode


class VectorStoreWriteError(RuntimeError):
    """Vector store write failed and should trigger rollback."""


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: dict[str, tuple[BaseNode, list[float]]] = {}

    def snapshot(self) -> dict[str, tuple[BaseNode, list[float]]]:
        return dict(self._records)

    def restore(self, snapshot: dict[str, tuple[BaseNode, list[float]]]) -> None:
        self._records = dict(snapshot)

    def upsert_nodes(
        self,
        nodes: Sequence[BaseNode],
        embeddings: Sequence[list[float]],
    ) -> None:
        if len(nodes) != len(embeddings):
            raise VectorStoreWriteError("nodes and embeddings length mismatch")
        for node, embedding in zip(nodes, embeddings):
            self._records[node.id_] = (node, embedding)

    def delete_by_ref_doc_id(self, ref_doc_id: str) -> int:
        deleted = [
            node_id
            for node_id, (node, _embedding) in self._records.items()
            if node.metadata.get("ref_doc_id") == ref_doc_id
        ]
        for node_id in deleted:
            del self._records[node_id]
        return len(deleted)

    def nodes_for_ref_doc_id(self, ref_doc_id: str) -> list[BaseNode]:
        return [
            node
            for node, _embedding in self._records.values()
            if node.metadata.get("ref_doc_id") == ref_doc_id
        ]
