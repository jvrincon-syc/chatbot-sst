from __future__ import annotations

import json
from collections.abc import Sequence

from llama_index.core.schema import BaseNode


class InMemoryNodeRepository:
    """Durable-node repository double for tests."""

    def __init__(self) -> None:
        self._nodes: dict[str, BaseNode] = {}

    def replace_document_nodes(
        self,
        *,
        document_id: str,
        nodes: Sequence[BaseNode],
    ) -> int:
        """Replace nodes by ref document id."""

        stale = [
            node_id
            for node_id, node in self._nodes.items()
            if node.metadata.get("ref_doc_id") == document_id
        ]
        for node_id in stale:
            del self._nodes[node_id]
        for node in nodes:
            self._nodes[node.id_] = node
        return len(stale)


class PostgresNodeRepository:
    """PostgreSQL adapter for parent and child node metadata/text."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def replace_document_nodes(
        self,
        *,
        document_id: str,
        nodes: Sequence[BaseNode],
    ) -> int:
        """Replace durable nodes for one normalized document."""

        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM indexing_nodes WHERE document_id = %s", (document_id,))
            deleted = cursor.rowcount
            for node in nodes:
                metadata = node.metadata
                cursor.execute(
                    """
                    INSERT INTO indexing_nodes (
                        node_id, document_id, source_relpath, source_hash,
                        ingestion_origin, node_role, parent_node_id, chunk_index,
                        page_start, page_end, section_title, section_path, text,
                        metadata, chunking_version, processing_fingerprint
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s
                    )
                    ON CONFLICT (node_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source_relpath = EXCLUDED.source_relpath,
                        source_hash = EXCLUDED.source_hash,
                        ingestion_origin = EXCLUDED.ingestion_origin,
                        node_role = EXCLUDED.node_role,
                        parent_node_id = EXCLUDED.parent_node_id,
                        chunk_index = EXCLUDED.chunk_index,
                        page_start = EXCLUDED.page_start,
                        page_end = EXCLUDED.page_end,
                        section_title = EXCLUDED.section_title,
                        section_path = EXCLUDED.section_path,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        chunking_version = EXCLUDED.chunking_version,
                        processing_fingerprint = EXCLUDED.processing_fingerprint,
                        updated_at = now()
                    """,
                    (
                        node.id_,
                        document_id,
                        metadata.get("source_relpath", ""),
                        metadata.get("source_hash", ""),
                        metadata.get("ingestion_origin", "local"),
                        metadata.get("node_role", "child"),
                        metadata.get("parent_node_id"),
                        metadata.get("chunk_index"),
                        metadata.get("page_start"),
                        metadata.get("page_end"),
                        metadata.get("section_title"),
                        metadata.get("section_path"),
                        node.text,
                        json.dumps(metadata, sort_keys=True),
                        metadata.get("chunking_version", ""),
                        metadata.get("processing_fingerprint", ""),
                    ),
                )
        return int(deleted)
