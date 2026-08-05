from __future__ import annotations

import json

from indexing.domain.models import IndexableDocument
from indexing.domain.profiles import IngestionOrigin


class InMemoryNormalizedDocumentRepository:
    """Normalized document repository double for tests."""

    def __init__(self) -> None:
        self.records: dict[str, tuple[IngestionOrigin, str, str]] = {}

    def replace_document(
        self,
        *,
        document: IndexableDocument,
        ingestion_origin: IngestionOrigin,
        artifact_fingerprint: str,
        corpus_version: str,
    ) -> None:
        """Record normalized document provenance."""

        self.records[document.document_id] = (
            ingestion_origin,
            artifact_fingerprint,
            corpus_version,
        )


class PostgresNormalizedDocumentRepository:
    """PostgreSQL adapter for normalized bundle provenance."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def replace_document(
        self,
        *,
        document: IndexableDocument,
        ingestion_origin: IngestionOrigin,
        artifact_fingerprint: str,
        corpus_version: str,
    ) -> None:
        """Upsert normalized document provenance and artifact references."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO indexing_normalized_documents (
                    document_id, source_relpath, source_hash, ingestion_origin,
                    corpus_version, processing_status, markdown_relpath,
                    metadata_relpath, pages_relpath, tables_relpath, forms_relpath,
                    artifact_fingerprint, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (document_id) DO UPDATE SET
                    source_relpath = EXCLUDED.source_relpath,
                    source_hash = EXCLUDED.source_hash,
                    ingestion_origin = EXCLUDED.ingestion_origin,
                    corpus_version = EXCLUDED.corpus_version,
                    processing_status = EXCLUDED.processing_status,
                    markdown_relpath = EXCLUDED.markdown_relpath,
                    metadata_relpath = EXCLUDED.metadata_relpath,
                    pages_relpath = EXCLUDED.pages_relpath,
                    tables_relpath = EXCLUDED.tables_relpath,
                    forms_relpath = EXCLUDED.forms_relpath,
                    artifact_fingerprint = EXCLUDED.artifact_fingerprint,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                (
                    document.document_id,
                    document.source_relpath,
                    document.source_hash,
                    ingestion_origin,
                    corpus_version,
                    document.document_status,
                    document.artifacts.markdown,
                    document.artifacts.metadata,
                    document.artifacts.pages,
                    document.artifacts.tables,
                    document.artifacts.forms,
                    artifact_fingerprint,
                    json.dumps(
                        {
                            "profile_id": document.profile.profile_id,
                            "chunking_version": document.profile.chunking_version,
                        },
                        sort_keys=True,
                    ),
                ),
            )
