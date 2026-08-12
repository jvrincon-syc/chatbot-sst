"""PostgreSQL adapters for the physical raw and normalized artifact catalogs.

The logical document and normalized-artifact repositories remain authoritative
for their existing identities. These adapters register filesystem artifacts as
auditable physical catalog rows and never issue DDL.
"""

from __future__ import annotations

import json

from rag_platform.domain.artifact_catalog import (
    NormalizedDocumentArtifactRecord,
    RawDocumentArtifactRecord,
)


class PostgresRawArtifactCatalogRepository:
    """Upserts ``project_raw_document_artifacts`` by immutable revision."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def upsert(self, record: RawDocumentArtifactRecord) -> RawDocumentArtifactRecord:
        """Register the raw filesystem artifact for its source revision."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO project_raw_document_artifacts"
                " (source_document_revision_id, project_id, logical_document_id,"
                " artifact_relpath, source_relpath, raw_content_hash, file_size,"
                " uploaded_by, uploaded_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (source_document_revision_id) DO UPDATE SET"
                " project_id = EXCLUDED.project_id,"
                " logical_document_id = EXCLUDED.logical_document_id,"
                " artifact_relpath = EXCLUDED.artifact_relpath,"
                " source_relpath = EXCLUDED.source_relpath,"
                " raw_content_hash = EXCLUDED.raw_content_hash,"
                " file_size = EXCLUDED.file_size,"
                " uploaded_by = EXCLUDED.uploaded_by,"
                " uploaded_at = EXCLUDED.uploaded_at",
                (
                    record.source_document_revision_id,
                    record.project_id,
                    record.logical_document_id,
                    str(record.artifact_relpath),
                    str(record.source_relpath),
                    record.raw_content_hash,
                    record.file_size,
                    record.uploaded_by,
                    record.uploaded_at,
                ),
            )
        return record


class PostgresNormalizedArtifactCatalogRepository:
    """Upserts ``project_normalized_document_artifacts`` by physical identity."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def upsert(
        self, record: NormalizedDocumentArtifactRecord
    ) -> NormalizedDocumentArtifactRecord:
        """Register physical normalized sidecars without changing their identity."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO project_normalized_document_artifacts"
                " (normalized_document_id, project_id, source_document_revision_id,"
                " logical_document_id, rag_variant_id, semantic_recipe_fingerprint,"
                " processing_profile_id, processing_profile_fingerprint,"
                " processing_origin, parser_provider, parser_engine, observed_revision,"
                " sanitized_config_json, schema_version, markdown_relpath,"
                " metadata_relpath, pages_relpath, tables_relpath, forms_relpath,"
                " source_hash, processing_status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (project_id, source_document_revision_id,"
                " processing_profile_fingerprint) DO UPDATE SET"
                " rag_variant_id = EXCLUDED.rag_variant_id,"
                " semantic_recipe_fingerprint = EXCLUDED.semantic_recipe_fingerprint,"
                " processing_profile_id = EXCLUDED.processing_profile_id,"
                " processing_origin = EXCLUDED.processing_origin,"
                " parser_provider = EXCLUDED.parser_provider,"
                " parser_engine = EXCLUDED.parser_engine,"
                " observed_revision = EXCLUDED.observed_revision,"
                " sanitized_config_json = EXCLUDED.sanitized_config_json,"
                " schema_version = EXCLUDED.schema_version,"
                " markdown_relpath = EXCLUDED.markdown_relpath,"
                " metadata_relpath = EXCLUDED.metadata_relpath,"
                " pages_relpath = EXCLUDED.pages_relpath,"
                " tables_relpath = EXCLUDED.tables_relpath,"
                " forms_relpath = EXCLUDED.forms_relpath,"
                " source_hash = EXCLUDED.source_hash,"
                " processing_status = EXCLUDED.processing_status",
                (
                    record.normalized_document_id,
                    record.project_id,
                    record.source_document_revision_id,
                    record.logical_document_id,
                    record.rag_variant_id,
                    record.semantic_recipe_fingerprint,
                    record.processing_profile_id,
                    record.processing_profile_fingerprint,
                    record.processing_origin.value,
                    record.parser_provider,
                    record.parser_engine,
                    record.observed_revision,
                    json.dumps(record.sanitized_config_json, sort_keys=True),
                    record.schema_version,
                    str(record.markdown_relpath),
                    str(record.metadata_relpath),
                    str(record.pages_relpath),
                    str(record.tables_relpath),
                    str(record.forms_relpath),
                    record.source_hash,
                    record.processing_status,
                ),
            )
        return record
