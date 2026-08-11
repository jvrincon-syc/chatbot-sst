"""PostgreSQL adapters for bundle-first indexing.

Every table already exists; this module only adapts the schema frozen by
``20260805_08`` .. ``20260805_11``. It never issues DDL and never interpolates a
value into SQL.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import json

from indexing.domain.bundle_first import (
    IndexingNodeRecord,
    IndexingRun,
    IndexingRunDocument,
)
from indexing.domain.errors import IndexingRunNotFound


_RUN_COLUMNS = (
    "run_id",
    "profile_id",
    "status",
    "config_hash",
    "embedding_bundle_id",
    "embedding_profile_id",
    "indexing_target_id",
    "corpus_version",
    "request_fingerprint",
    "idempotency_key",
    "validation_status",
    "activation_status",
    "owner_id",
    "lease_expires_at",
    "started_at",
    "completed_at",
    "summary",
    "warnings",
)

_RUN_DOCUMENT_COLUMNS = (
    "run_id",
    "document_id",
    "source_relpath",
    "source_hash",
    "ingestion_origin",
    "eligibility_status",
    "eligibility_reason",
    "indexed_parent_nodes",
    "indexed_child_nodes",
    "error_code",
    "source_chunk_bundle_id",
    "embedding_bundle_id",
    "status",
    "parent_count",
    "child_count",
    "vector_count",
    "started_at",
    "completed_at",
    "committed_at",
    "internal_error_id",
)


def _row_to_mapping(
    row: Mapping[str, object] | Sequence[object],
    columns: tuple[str, ...],
) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip(columns, row))


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, (str, bytes)):
        return dict(json.loads(value))
    return dict(value)  # type: ignore[arg-type]


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(item) for item in json.loads(value)]
    return [str(item) for item in value]  # type: ignore[union-attr]


class PsycopgTransactionManager:
    """Scope one durable commit around a psycopg connection."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit on success, roll back on any exception."""

        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()


class PostgresIndexingNodeWriter:
    """Persist neutral node records into ``indexing_nodes``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def replace_document_nodes(
        self,
        *,
        document_id: str,
        nodes: Sequence[IndexingNodeRecord],
    ) -> int:
        """Replace the durable nodes of one document.

        Parents are written before children so the deferred self foreign key
        added by ``20260805_10`` always resolves inside the same transaction.
        """

        ordered = [node for node in nodes if node.node_role == "parent"] + [
            node for node in nodes if node.node_role == "child"
        ]
        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM indexing_nodes WHERE document_id = %s",
                (document_id,),
            )
            deleted = cursor.rowcount
            for node in ordered:
                cursor.execute(
                    """
                    INSERT INTO indexing_nodes (
                        node_id, document_id, source_relpath, source_hash,
                        ingestion_origin, node_role, parent_node_id, chunk_index,
                        page_start, page_end, section_title, section_path, text,
                        metadata, chunking_version, processing_fingerprint,
                        source_chunk_bundle_id, chunking_bundle_fingerprint,
                        corpus_version
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s, %s
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
                        source_chunk_bundle_id = EXCLUDED.source_chunk_bundle_id,
                        chunking_bundle_fingerprint = EXCLUDED.chunking_bundle_fingerprint,
                        corpus_version = EXCLUDED.corpus_version,
                        updated_at = now()
                    """,
                    (
                        node.node_id,
                        node.document_id,
                        node.source_relpath,
                        node.source_hash,
                        node.ingestion_origin,
                        node.node_role,
                        node.parent_node_id,
                        node.chunk_index,
                        node.page_start,
                        node.page_end,
                        node.section_title,
                        node.section_path,
                        node.text,
                        json.dumps(node.metadata, sort_keys=True, default=str),
                        node.chunking_version,
                        node.processing_fingerprint,
                        node.source_chunk_bundle_id,
                        node.chunking_bundle_fingerprint,
                        node.corpus_version,
                    ),
                )
        return int(deleted)

    def replace_scoped_nodes(
        self,
        *,
        project_id: str,
        source_chunk_bundle_id: str,
        nodes: Sequence[IndexingNodeRecord],
    ) -> int:
        """Replace the platform nodes of one bundle within one project (ADR-007 §2).

        Deletion is scoped by ``(project_id, source_chunk_bundle_id)`` so it never
        touches another project's or bundle's rows. Parents are inserted before
        children so the deferred self FK resolves inside the same transaction. The
        physical-identity columns (``project_id``/``source_chunk_id``/
        ``source_parent_chunk_id``) are written explicitly; ``node_id``/
        ``parent_node_id`` are the namespaced physical ids computed by ``build_nodes``.
        """

        ordered = [node for node in nodes if node.node_role == "parent"] + [
            node for node in nodes if node.node_role == "child"
        ]
        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM indexing_nodes"
                " WHERE project_id = %s AND source_chunk_bundle_id = %s",
                (project_id, source_chunk_bundle_id),
            )
            deleted = cursor.rowcount
            for node in ordered:
                cursor.execute(
                    """
                    INSERT INTO indexing_nodes (
                        node_id, project_id, document_id, source_relpath, source_hash,
                        ingestion_origin, node_role, parent_node_id,
                        source_chunk_id, source_parent_chunk_id, chunk_index,
                        page_start, page_end, section_title, section_path, text,
                        metadata, chunking_version, processing_fingerprint,
                        source_chunk_bundle_id, chunking_bundle_fingerprint,
                        corpus_version
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s::jsonb, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (node_id) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        document_id = EXCLUDED.document_id,
                        source_relpath = EXCLUDED.source_relpath,
                        source_hash = EXCLUDED.source_hash,
                        ingestion_origin = EXCLUDED.ingestion_origin,
                        node_role = EXCLUDED.node_role,
                        parent_node_id = EXCLUDED.parent_node_id,
                        source_chunk_id = EXCLUDED.source_chunk_id,
                        source_parent_chunk_id = EXCLUDED.source_parent_chunk_id,
                        chunk_index = EXCLUDED.chunk_index,
                        page_start = EXCLUDED.page_start,
                        page_end = EXCLUDED.page_end,
                        section_title = EXCLUDED.section_title,
                        section_path = EXCLUDED.section_path,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        chunking_version = EXCLUDED.chunking_version,
                        processing_fingerprint = EXCLUDED.processing_fingerprint,
                        source_chunk_bundle_id = EXCLUDED.source_chunk_bundle_id,
                        chunking_bundle_fingerprint = EXCLUDED.chunking_bundle_fingerprint,
                        corpus_version = EXCLUDED.corpus_version,
                        updated_at = now()
                    """,
                    (
                        node.node_id,
                        node.project_id,
                        node.document_id,
                        node.source_relpath,
                        node.source_hash,
                        node.ingestion_origin,
                        node.node_role,
                        node.parent_node_id,
                        node.source_chunk_id,
                        node.source_parent_chunk_id,
                        node.chunk_index,
                        node.page_start,
                        node.page_end,
                        node.section_title,
                        node.section_path,
                        node.text,
                        json.dumps(node.metadata, sort_keys=True, default=str),
                        node.chunking_version,
                        node.processing_fingerprint,
                        node.source_chunk_bundle_id,
                        node.chunking_bundle_fingerprint,
                        node.corpus_version,
                    ),
                )
        return int(deleted)


class PostgresIndexingRunRepository:
    """Durable ``indexing_runs`` ledger with a transactional claim."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def create(self, run: IndexingRun) -> IndexingRun:
        """Insert a run."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO indexing_runs (
                    run_id, profile_id, status, config_hash, embedding_bundle_id,
                    embedding_profile_id, indexing_target_id, corpus_version,
                    request_fingerprint, idempotency_key, validation_status,
                    activation_status, summary, warnings
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    run.run_id,
                    run.profile_id,
                    run.status,
                    run.config_hash,
                    run.embedding_bundle_id,
                    run.embedding_profile_id,
                    run.indexing_target_id,
                    run.corpus_version,
                    run.request_fingerprint,
                    run.idempotency_key,
                    run.validation_status,
                    run.activation_status,
                    json.dumps(run.summary, sort_keys=True, default=str),
                    json.dumps(run.warnings),
                ),
            )
        return self.get(run.run_id)

    def get(self, run_id: str) -> IndexingRun:
        """Return one run or raise ``IndexingRunNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM indexing_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise IndexingRunNotFound(f"indexing run not found: {run_id}")
        return _run_from_row(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> IndexingRun | None:
        """Return the run stored under one idempotency key."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM indexing_runs"
                " WHERE idempotency_key = %s ORDER BY started_at DESC LIMIT 1",
                (idempotency_key,),
            )
            row = cursor.fetchone()
        return None if row is None else _run_from_row(row)

    def list_runs(self) -> list[IndexingRun]:
        """Return every run, newest first."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM indexing_runs"
                " ORDER BY started_at DESC"
            )
            rows = cursor.fetchall()
        return [_run_from_row(row) for row in rows]

    def claim(self, run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE indexing_runs
                   SET status = 'running', started_at = now()
                 WHERE run_id = %s AND status = 'pending'
                """,
                (run_id,),
            )
            return int(cursor.rowcount) == 1

    def update(self, run: IndexingRun) -> IndexingRun:
        """Persist a durable state transition."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE indexing_runs
                   SET status = %s,
                       validation_status = %s,
                       activation_status = %s,
                       completed_at = %s,
                       owner_id = %s,
                       lease_expires_at = %s,
                       summary = %s::jsonb,
                       warnings = %s::jsonb
                 WHERE run_id = %s
                """,
                (
                    run.status,
                    run.validation_status,
                    run.activation_status,
                    run.completed_at,
                    run.owner_id,
                    run.lease_expires_at,
                    json.dumps(run.summary, sort_keys=True, default=str),
                    json.dumps(run.warnings),
                    run.run_id,
                ),
            )
        return self.get(run.run_id)

    def list_running(self) -> list[IndexingRun]:
        """Return runs currently marked ``running``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM indexing_runs"
                " WHERE status = 'running'"
            )
            rows = cursor.fetchall()
        return [_run_from_row(row) for row in rows]


def _run_from_row(row: Mapping[str, object] | Sequence[object]) -> IndexingRun:
    values = _row_to_mapping(row, _RUN_COLUMNS)
    return IndexingRun.model_validate(
        {
            **{
                key: values[key]
                for key in _RUN_COLUMNS
                if key not in {"summary", "warnings"}
            },
            "summary": _json_object(values["summary"]),
            "warnings": _json_list(values["warnings"]),
        }
    )


class PostgresIndexingRunDocumentRepository:
    """Durable ``indexing_run_documents`` ledger."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def upsert(self, document: IndexingRunDocument) -> IndexingRunDocument:
        """Insert or update one per-document row."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO indexing_run_documents (
                    run_id, document_id, source_relpath, source_hash,
                    ingestion_origin, eligibility_status, eligibility_reason,
                    indexed_parent_nodes, indexed_child_nodes, error_code,
                    source_chunk_bundle_id, embedding_bundle_id, status,
                    parent_count, child_count, vector_count, started_at,
                    completed_at, committed_at, internal_error_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (run_id, document_id) DO UPDATE SET
                    indexed_parent_nodes = EXCLUDED.indexed_parent_nodes,
                    indexed_child_nodes = EXCLUDED.indexed_child_nodes,
                    error_code = EXCLUDED.error_code,
                    source_chunk_bundle_id = EXCLUDED.source_chunk_bundle_id,
                    embedding_bundle_id = EXCLUDED.embedding_bundle_id,
                    status = EXCLUDED.status,
                    parent_count = EXCLUDED.parent_count,
                    child_count = EXCLUDED.child_count,
                    vector_count = EXCLUDED.vector_count,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    committed_at = EXCLUDED.committed_at,
                    internal_error_id = EXCLUDED.internal_error_id
                """,
                (
                    document.run_id,
                    document.document_id,
                    document.source_relpath,
                    document.source_hash,
                    document.ingestion_origin,
                    document.eligibility_status,
                    document.eligibility_reason,
                    document.indexed_parent_nodes,
                    document.indexed_child_nodes,
                    document.error_code,
                    document.source_chunk_bundle_id,
                    document.embedding_bundle_id,
                    document.status,
                    document.parent_count,
                    document.child_count,
                    document.vector_count,
                    document.started_at,
                    document.completed_at,
                    document.committed_at,
                    document.internal_error_id,
                ),
            )
        return document

    def list_for_run(self, run_id: str) -> list[IndexingRunDocument]:
        """Return every document row of one run."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_DOCUMENT_COLUMNS)} FROM indexing_run_documents"
                " WHERE run_id = %s ORDER BY document_id",
                (run_id,),
            )
            rows = cursor.fetchall()
        return [
            IndexingRunDocument.model_validate(
                _row_to_mapping(row, _RUN_DOCUMENT_COLUMNS)
            )
            for row in rows
        ]
