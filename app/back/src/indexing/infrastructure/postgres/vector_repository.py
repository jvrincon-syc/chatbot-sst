from __future__ import annotations

import json
from collections.abc import Sequence

from llama_index.core.schema import BaseNode

from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError


class InMemoryVectorRepository:
    """Profile-aware vector repository for contract tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], tuple[BaseNode, list[float]]] = {}

    def replace_document_vectors(
        self,
        *,
        document_id: str,
        profile: ResolvedIndexingProfile,
        nodes: Sequence[BaseNode],
        embeddings: Sequence[list[float]],
    ) -> int:
        """Replace vectors for one document and one profile only."""

        _validate_embeddings(profile=profile, nodes=nodes, embeddings=embeddings)
        stale_keys = [
            key
            for key in self._records
            if key[0] == document_id and key[1] == profile.profile_id
        ]
        for key in stale_keys:
            del self._records[key]
        for node, embedding in zip(nodes, embeddings):
            self._records[(document_id, profile.profile_id, node.id_)] = (
                node,
                list(embedding),
            )
        return len(stale_keys)

    def count(self, *, document_id: str, profile: ResolvedIndexingProfile) -> int:
        """Count vectors stored for one document/profile pair."""

        return sum(
            1
            for stored_document_id, stored_profile_id, _node_id in self._records
            if stored_document_id == document_id and stored_profile_id == profile.profile_id
        )


class PostgresVectorRepository:
    """PostgreSQL adapter for profile-specific vector tables."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def replace_document_vectors(
        self,
        *,
        document_id: str,
        profile: ResolvedIndexingProfile,
        nodes: Sequence[BaseNode],
        embeddings: Sequence[list[float]],
    ) -> int:
        """Replace vectors inside the selected profile table."""

        _validate_embeddings(profile=profile, nodes=nodes, embeddings=embeddings)
        table = profile.vector_table
        with self._connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table} WHERE document_id = %s", (document_id,))
            deleted = cursor.rowcount
            for node, embedding in zip(nodes, embeddings):
                cursor.execute(
                    f"""
                    INSERT INTO {table} (node_id, document_id, embedding, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (node_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    (
                        node.id_,
                        document_id,
                        embedding,
                        json.dumps(node.metadata, sort_keys=True),
                    ),
                )
        return int(deleted)


def _validate_embeddings(
    *,
    profile: ResolvedIndexingProfile,
    nodes: Sequence[BaseNode],
    embeddings: Sequence[list[float]],
) -> None:
    if len(nodes) != len(embeddings):
        raise VectorStoreWriteError("nodes and embeddings length mismatch")
    for embedding in embeddings:
        if len(embedding) != profile.embedding_dimension:
            raise VectorStoreWriteError(
                "embedding dimension does not match selected profile"
            )
