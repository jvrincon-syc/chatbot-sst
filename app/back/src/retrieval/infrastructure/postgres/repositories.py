"""PostgreSQL adapters for retrieval profiles, pgvector search and FTS.

The physical vector table always comes from ``indexing_targets`` and is
validated against the ``idx_vec_[a-z0-9_]+`` pattern before it can be
interpolated into an identifier position; every value stays parameterized.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import re

from retrieval.domain.errors import RetrievalProfileNotFound
from retrieval.domain.models import RetrievalProfile, RetrievedEvidence


_VECTOR_TABLE_PATTERN = re.compile(r"^idx_vec_[a-z0-9_]+$")

#: pgvector distance operator per semantic metric.
_DISTANCE_OPERATOR = {
    "cosine": "<=>",
    "l2": "<->",
    "inner_product": "<#>",
}

_PROFILE_COLUMNS = (
    "retrieval_profile_id",
    "consumer_scope_type",
    "consumer_scope_id",
    "corpus_version",
    "embedding_profile_id",
    "indexing_target_id",
    "lexical_fallback_policy",
    "active",
    "validation_status",
    "validated_at",
    "last_runtime_status",
    "created_at",
    "deprecated_at",
)


def _validated_table(vector_table: str) -> str:
    if not _VECTOR_TABLE_PATTERN.match(vector_table):
        raise ValueError("vector table name is not a registered indexing target table")
    return vector_table


def _row_to_mapping(
    row: Mapping[str, object] | Sequence[object],
    columns: tuple[str, ...],
) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip(columns, row))


class PostgresRetrievalProfileRepository:
    """Durable ``retrieval_profiles`` ledger, the authority over activation."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def upsert(self, profile: RetrievalProfile) -> RetrievalProfile:
        """Insert or update one retrieval profile."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO retrieval_profiles (
                    retrieval_profile_id, consumer_scope_type, consumer_scope_id,
                    corpus_version, embedding_profile_id, indexing_target_id,
                    lexical_fallback_policy, active, validation_status,
                    validated_at, last_runtime_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (retrieval_profile_id) DO UPDATE SET
                    lexical_fallback_policy = EXCLUDED.lexical_fallback_policy,
                    validation_status = EXCLUDED.validation_status,
                    validated_at = EXCLUDED.validated_at,
                    last_runtime_status = EXCLUDED.last_runtime_status
                """,
                (
                    profile.retrieval_profile_id,
                    profile.consumer_scope_type,
                    profile.consumer_scope_id,
                    profile.corpus_version,
                    profile.embedding_profile_id,
                    profile.indexing_target_id,
                    profile.lexical_fallback_policy,
                    profile.active,
                    profile.validation_status,
                    profile.validated_at,
                    profile.last_runtime_status,
                ),
            )
        return self.get(profile.retrieval_profile_id)

    def get(self, retrieval_profile_id: str) -> RetrievalProfile:
        """Return one profile or raise ``RetrievalProfileNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_PROFILE_COLUMNS)} FROM retrieval_profiles"
                " WHERE retrieval_profile_id = %s",
                (retrieval_profile_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RetrievalProfileNotFound(
                f"retrieval profile not found: {retrieval_profile_id}"
            )
        return RetrievalProfile.model_validate(_row_to_mapping(row, _PROFILE_COLUMNS))

    def list_profiles(self) -> list[RetrievalProfile]:
        """Return every retrieval profile."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_PROFILE_COLUMNS)} FROM retrieval_profiles"
                " ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
        return [
            RetrievalProfile.model_validate(_row_to_mapping(row, _PROFILE_COLUMNS))
            for row in rows
        ]

    def find_active(
        self,
        *,
        consumer_scope_type: str,
        consumer_scope_id: str,
        corpus_version: str | None = None,
    ) -> RetrievalProfile | None:
        """Return the single active profile of one consumer scope."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {', '.join(_PROFILE_COLUMNS)} FROM retrieval_profiles
                 WHERE consumer_scope_type = %s
                   AND consumer_scope_id = %s
                   AND (%s::text IS NULL OR corpus_version = %s)
                   AND active = true
                 LIMIT 1
                """,
                (consumer_scope_type, consumer_scope_id, corpus_version, corpus_version),
            )
            row = cursor.fetchone()
        return (
            None
            if row is None
            else RetrievalProfile.model_validate(_row_to_mapping(row, _PROFILE_COLUMNS))
        )

    def activate(
        self,
        *,
        retrieval_profile_id: str,
        validated_at: datetime,
    ) -> RetrievalProfile:
        """Activate one profile and deactivate the previous one in the scope.

        Both statements run in the caller's transaction so the partial unique
        index ``idx_retrieval_profiles_one_active_scope_corpus`` never sees two
        active rows for the same scope.
        """

        profile = self.get(retrieval_profile_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE retrieval_profiles
                   SET active = false
                 WHERE consumer_scope_type = %s
                   AND consumer_scope_id = %s
                   AND corpus_version = %s
                   AND retrieval_profile_id <> %s
                   AND active = true
                """,
                (
                    profile.consumer_scope_type,
                    profile.consumer_scope_id,
                    profile.corpus_version,
                    retrieval_profile_id,
                ),
            )
            cursor.execute(
                """
                UPDATE retrieval_profiles
                   SET active = true,
                       validation_status = 'passed',
                       validated_at = %s
                 WHERE retrieval_profile_id = %s
                """,
                (validated_at, retrieval_profile_id),
            )
        return self.get(retrieval_profile_id)

    def record_runtime_status(
        self,
        *,
        retrieval_profile_id: str,
        last_runtime_status: str,
    ) -> RetrievalProfile:
        """Persist the outcome of the latest retrieval attempt."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE retrieval_profiles SET last_runtime_status = %s"
                " WHERE retrieval_profile_id = %s",
                (last_runtime_status, retrieval_profile_id),
            )
        return self.get(retrieval_profile_id)


class PostgresVectorSearch:
    """pgvector search restricted to the active rows of one lane."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def search(
        self,
        *,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
        distance_metric: str,
        query_embedding: Sequence[float],
        top_k: int,
    ) -> list[RetrievedEvidence]:
        """Return the closest active child chunks of one lane."""

        table = _validated_table(vector_table)
        operator = _DISTANCE_OPERATOR[distance_metric]
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT vector_row.node_id,
                       vector_row.document_id,
                       vector_row.embedding_bundle_id,
                       node.parent_node_id,
                       node.text,
                       node.page_start,
                       node.page_end,
                       node.section_title,
                       node.section_path,
                       node.metadata,
                       1 - (vector_row.embedding {operator} %s::vector) AS score
                  FROM {table} AS vector_row
                  JOIN indexing_nodes AS node ON node.node_id = vector_row.node_id
                  JOIN indexing_normalized_documents AS document
                    ON document.document_id = vector_row.document_id
                 WHERE vector_row.is_active = true
                   AND vector_row.embedding_profile_id = %s
                   AND vector_row.indexing_target_id = %s
                   AND vector_row.corpus_version = %s
                   AND document.processing_status = 'processed'
                   AND document.review_status = 'approved'
                 ORDER BY vector_row.embedding {operator} %s::vector
                 LIMIT %s
                """,
                (
                    list(query_embedding),
                    embedding_profile_id,
                    indexing_target_id,
                    corpus_version,
                    list(query_embedding),
                    top_k,
                ),
            )
            rows = cursor.fetchall()
        return [
            _evidence_from_row(
                row=row,
                source="vector",
                embedding_profile_id=embedding_profile_id,
                corpus_version=corpus_version,
            )
            for row in rows
        ]

    def count_active_rows(
        self,
        *,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> int:
        """Count the active vector rows currently serving one lane."""

        table = _validated_table(vector_table)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT count(*) FROM {table}
                 WHERE is_active = true
                   AND embedding_profile_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                """,
                (embedding_profile_id, indexing_target_id, corpus_version),
            )
            row = cursor.fetchone()
        if row is None:
            return 0
        return int(row["count"] if isinstance(row, Mapping) else row[0])

    def active_bundle_ids(
        self,
        *,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> list[str]:
        """Return the embedding bundle ids currently active in one lane."""

        table = _validated_table(vector_table)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT embedding_bundle_id FROM {table}
                 WHERE is_active = true
                   AND embedding_profile_id = %s
                   AND indexing_target_id = %s
                   AND corpus_version = %s
                """,
                (embedding_profile_id, indexing_target_id, corpus_version),
            )
            rows = cursor.fetchall()
        return sorted(
            str(row["embedding_bundle_id"] if isinstance(row, Mapping) else row[0])
            for row in rows
            if (row["embedding_bundle_id"] if isinstance(row, Mapping) else row[0])
        )


class PostgresLexicalSearch:
    """Full-text search over ``indexing_nodes`` child rows."""

    def __init__(self, connection: object, *, embedding_profile_id: str) -> None:
        self._connection = connection
        self._embedding_profile_id = embedding_profile_id

    def search(
        self,
        *,
        query: str,
        corpus_version: str,
        top_k: int,
    ) -> list[RetrievedEvidence]:
        """Return the closest child nodes by full-text rank."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT node.node_id,
                       node.document_id,
                       NULL AS embedding_bundle_id,
                       node.parent_node_id,
                       node.text,
                       node.page_start,
                       node.page_end,
                       node.section_title,
                       node.section_path,
                       node.metadata,
                       ts_rank(
                           to_tsvector('spanish', node.text),
                           plainto_tsquery('spanish', %s)
                       ) AS score
                  FROM indexing_nodes AS node
                  JOIN indexing_normalized_documents AS document
                    ON document.document_id = node.document_id
                 WHERE node.node_role = 'child'
                   AND node.corpus_version = %s
                   AND document.processing_status = 'processed'
                   AND document.review_status = 'approved'
                   AND to_tsvector('spanish', node.text)
                       @@ plainto_tsquery('spanish', %s)
                 ORDER BY score DESC
                 LIMIT %s
                """,
                (query, corpus_version, query, top_k),
            )
            rows = cursor.fetchall()
        return [
            _evidence_from_row(
                row=row,
                source="lexical",
                embedding_profile_id=self._embedding_profile_id,
                corpus_version=corpus_version,
            )
            for row in rows
        ]


class PostgresParentExpansion:
    """Expand retrieved child evidence into its parent node."""

    def __init__(self, connection: object, *, embedding_profile_id: str) -> None:
        self._connection = connection
        self._embedding_profile_id = embedding_profile_id

    def expand(
        self,
        *,
        parent_node_ids: Sequence[str],
        corpus_version: str,
    ) -> dict[str, RetrievedEvidence]:
        """Return parent evidence keyed by ``parent_node_id``."""

        if not parent_node_ids:
            return {}
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT node.node_id,
                       node.document_id,
                       NULL AS embedding_bundle_id,
                       node.parent_node_id,
                       node.text,
                       node.page_start,
                       node.page_end,
                       node.section_title,
                       node.section_path,
                       node.metadata,
                       0.0 AS score
                  FROM indexing_nodes AS node
                 WHERE node.node_id = ANY(%s)
                   AND node.node_role = 'parent'
                   AND node.corpus_version = %s
                """,
                (list(parent_node_ids), corpus_version),
            )
            rows = cursor.fetchall()
        parents: dict[str, RetrievedEvidence] = {}
        for row in rows:
            evidence = _evidence_from_row(
                row=row,
                source="lexical",
                embedding_profile_id=self._embedding_profile_id,
                corpus_version=corpus_version,
            )
            parents[evidence.node_id] = evidence
        return parents


_EVIDENCE_COLUMNS = (
    "node_id",
    "document_id",
    "embedding_bundle_id",
    "parent_node_id",
    "text",
    "page_start",
    "page_end",
    "section_title",
    "section_path",
    "metadata",
    "score",
)


def _evidence_from_row(
    *,
    row: Mapping[str, object] | Sequence[object],
    source: str,
    embedding_profile_id: str,
    corpus_version: str,
) -> RetrievedEvidence:
    values = _row_to_mapping(row, _EVIDENCE_COLUMNS)
    metadata = values["metadata"]
    return RetrievedEvidence(
        node_id=str(values["node_id"]),
        document_id=str(values["document_id"]),
        parent_node_id=(
            None if values["parent_node_id"] is None else str(values["parent_node_id"])
        ),
        child_chunk_id=str(values["node_id"]),
        text=str(values["text"]),
        score=float(values["score"]),
        source=source,  # type: ignore[arg-type]
        page_start=values["page_start"],  # type: ignore[arg-type]
        page_end=values["page_end"],  # type: ignore[arg-type]
        section_title=values["section_title"],  # type: ignore[arg-type]
        section_path=values["section_path"],  # type: ignore[arg-type]
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        embedding_profile_id=embedding_profile_id,
        corpus_version=corpus_version,
        embedding_bundle_id=(
            None
            if values["embedding_bundle_id"] is None
            else str(values["embedding_bundle_id"])
        ),
    )
