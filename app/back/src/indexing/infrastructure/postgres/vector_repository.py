from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from llama_index.core.schema import BaseNode

from embedding.infrastructure.postgres.repositories import PostgresIndexingTargetRepository
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from indexing.infrastructure.postgres.profile_registry import (
    PostgresProfileRegistry,
    safe_vector_table_identifier,
)
from psycopg2 import sql


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


@dataclass(frozen=True)
class AppendOnlyVectorRecord:
    """One inactive vector row ready to be activated after validation."""

    node_id: str
    document_id: str
    embedding: list[float]
    metadata: dict[str, object]
    embedding_bundle_id: str
    corpus_version: str
    configuration_fingerprint: str
    vector_checksum: str
    # ADR-008 pure-platform: propiedad de proyecto obligatoria en la fila vectorial
    # (la BD la exige NOT NULL; el FK compuesto ya no se bypassa).
    project_id: str


class PostgresVectorRepository:
    """PostgreSQL adapter for profile-specific vector tables."""

    def __init__(self, connection: object) -> None:
        self._connection = connection
        self._profiles = PostgresProfileRegistry(connection)
        self._targets = PostgresIndexingTargetRepository(connection)

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
        table_identifier = sql.Identifier(profile.vector_table)
        with self._connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE document_id = %s").format(table_identifier),
                (document_id,),
            )
            deleted = cursor.rowcount
            for node, embedding in zip(nodes, embeddings):
                cursor.execute(
                    sql.SQL(
                        """
                    INSERT INTO {} (node_id, document_id, embedding, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (node_id) WHERE embedding_bundle_id IS NULL DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """
                    ).format(table_identifier),
                    (
                        node.id_,
                        document_id,
                        embedding,
                        json.dumps(node.metadata, sort_keys=True),
                    ),
                )
        return int(deleted)

    def append_bundle_vectors(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        records: Sequence[AppendOnlyVectorRecord],
    ) -> int:
        """Insert inactive vector rows for one embedding bundle."""

        if not records:
            return 0
        for record in records:
            if len(record.embedding) != profile.embedding_dimension:
                raise VectorStoreWriteError(
                    "embedding dimension does not match selected profile"
                )

        table_identifier = safe_vector_table_identifier(
            profile_id=profile.profile_id,
            indexing_target_id=indexing_target_id,
            registry=self._profiles,
            targets=self._targets,
        )
        with self._connection.cursor() as cursor:
            for record in records:
                cursor.execute(
                    sql.SQL(
                        """
                    INSERT INTO {} (
                        node_id, project_id, document_id, embedding, metadata,
                        embedding_bundle_id, embedding_profile_id,
                        indexing_target_id, corpus_version, is_active,
                        configuration_fingerprint, vector_checksum
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (embedding_bundle_id, node_id) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        document_id = EXCLUDED.document_id,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        embedding_profile_id = EXCLUDED.embedding_profile_id,
                        indexing_target_id = EXCLUDED.indexing_target_id,
                        corpus_version = EXCLUDED.corpus_version,
                        is_active = false,
                        superseded_at = NULL,
                        configuration_fingerprint = EXCLUDED.configuration_fingerprint,
                        vector_checksum = EXCLUDED.vector_checksum,
                        updated_at = now()
                    """
                    ).format(table_identifier),
                    (
                        record.node_id,
                        record.project_id,
                        record.document_id,
                        record.embedding,
                        json.dumps(record.metadata, sort_keys=True),
                        record.embedding_bundle_id,
                        profile.profile_id,
                        indexing_target_id,
                        record.corpus_version,
                        False,
                        record.configuration_fingerprint,
                        record.vector_checksum,
                    ),
                )
        return len(records)

    def activate_bundle(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> None:
        """Activate one bundle and supersede prior active rows of the same documents."""

        table_identifier = safe_vector_table_identifier(
            profile_id=profile.profile_id,
            indexing_target_id=indexing_target_id,
            registry=self._profiles,
            targets=self._targets,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                UPDATE {}
                   SET is_active = false,
                       superseded_at = now()
                 WHERE embedding_profile_id = %s
                   AND project_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                   AND document_id IN (
                       SELECT DISTINCT document_id
                         FROM {}
                        WHERE embedding_profile_id = %s
                          AND project_id = %s
                          AND indexing_target_id = %s
                          AND corpus_version = %s
                          AND embedding_bundle_id = %s
                   )
                   AND embedding_bundle_id <> %s
                   AND is_active = true
                """
                ).format(table_identifier, table_identifier),
                (
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    embedding_bundle_id,
                    embedding_bundle_id,
                ),
            )
            cursor.execute(
                sql.SQL(
                    """
                UPDATE {}
                   SET is_active = true,
                       superseded_at = NULL
                 WHERE embedding_profile_id = %s
                   AND project_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                   AND embedding_bundle_id = %s
                """
                ).format(table_identifier),
                (
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    embedding_bundle_id,
                ),
            )

    def count_active_rows(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> int:
        """Count active vector rows of one bundle inside one lane."""

        table_identifier = safe_vector_table_identifier(
            profile_id=profile.profile_id,
            indexing_target_id=indexing_target_id,
            registry=self._profiles,
            targets=self._targets,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                SELECT count(*) FROM {}
                 WHERE embedding_profile_id = %s
                   AND project_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                   AND embedding_bundle_id = %s
                   AND is_active = true
                """
                ).format(table_identifier),
                (
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    embedding_bundle_id,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            return 0
        return int(row["count"] if isinstance(row, Mapping) else row[0])

    def rollback_to_bundle(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        current_embedding_bundle_id: str,
        previous_embedding_bundle_id: str,
    ) -> None:
        """Deactivate the current bundle and reactivate a previous validated bundle."""

        table_identifier = safe_vector_table_identifier(
            profile_id=profile.profile_id,
            indexing_target_id=indexing_target_id,
            registry=self._profiles,
            targets=self._targets,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                UPDATE {}
                   SET is_active = false,
                       superseded_at = now()
                 WHERE embedding_profile_id = %s
                   AND project_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                   AND embedding_bundle_id = %s
                """
                ).format(table_identifier),
                (
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    current_embedding_bundle_id,
                ),
            )
            cursor.execute(
                sql.SQL(
                    """
                UPDATE {}
                   SET is_active = true,
                       superseded_at = NULL
                 WHERE embedding_profile_id = %s
                   AND project_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                   AND embedding_bundle_id = %s
                """
                ).format(table_identifier),
                (
                    profile.profile_id,
                    project_id,
                    indexing_target_id,
                    corpus_version,
                    previous_embedding_bundle_id,
                ),
            )


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
