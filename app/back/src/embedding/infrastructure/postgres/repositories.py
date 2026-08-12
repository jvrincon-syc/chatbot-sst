"""PostgreSQL adapters for the bundle-first embedding ledgers.

Every statement is parameterized and every table already exists: this module
adapts the schema frozen by migrations ``20260805_01`` .. ``20260805_15`` and
never issues DDL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json

from embedding.domain.errors import (
    ChunkBundleNotFound,
    EmbeddingBundleInvalid,
    EmbeddingBundleNotFound,
    EmbeddingProfileNotFound,
    EmbeddingRunNotFound,
)
from embedding.domain.models import (
    ChunkBundleRef,
    EmbeddingBundle,
    EmbeddingBundleChunk,
    EmbeddingProfile,
    EmbeddingRun,
    ReadinessCheck,
)
from ingestion.paths import ArtifactPaths
from indexing.domain.bundle_first import IndexingTarget


_PROFILE_COLUMNS = (
    "profile_id",
    "ingestion_origin",
    "chunking_version",
    "embedding_provider",
    "embedding_model",
    "model_revision",
    "embedding_dimension",
    "normalization",
    "distance_metric",
    "configuration_fingerprint",
    "semantic_config_json",
    "vector_table",
    "metadata_schema_version",
    "config_hash",
    "default_indexing_target_id",
    "active",
    "document_enabled",
    "query_enabled",
    "compatibility_status",
    "deprecated_at",
)

_TARGET_COLUMNS = (
    "indexing_target_id",
    "postgres_schema",
    "vector_table",
    "distance_ops",
    "storage_schema_version",
    "active",
    "created_at",
    "deprecated_at",
)

_CHUNK_BUNDLE_COLUMNS = (
    "chunk_bundle_id",
    "project_id",
    "bundle_fingerprint",
    "profile_id",
    "profile_fingerprint",
    "corpus_version",
    "source_document_id",
    "artifact_relpath",
    "parent_count",
    "child_count",
    "status",
    "rag_variant_id",
    "semantic_recipe_fingerprint",
)

_RUN_COLUMNS = (
    "embedding_run_id",
    "idempotency_key",
    "request_fingerprint",
    "source_chunk_bundle_id",
    "embedding_profile_id",
    "configuration_fingerprint",
    "project_id",
    "rag_variant_id",
    "rag_release_id",
    "runtime_engine",
    "runtime_mode",
    "engine_revision_observed",
    "status",
    "started_at",
    "completed_at",
    "summary_json",
    "warnings_json",
    "error_summary",
    "produced_embedding_bundle_id",
    "created_at",
)

_BUNDLE_COLUMNS = (
    "embedding_bundle_id",
    "project_id",
    "source_chunk_bundle_id",
    "embedding_profile_id",
    "provider",
    "model",
    "model_revision",
    "dimension",
    "normalization",
    "distance_metric",
    "configuration_fingerprint",
    "corpus_version",
    "semantic_config_json",
    "bundle_schema_version",
    "source_content_fingerprint",
    "vector_artifact_relpath",
    "chunk_map_relpath",
    "vector_dtype",
    "vector_shape",
    "vector_count",
    "checksums_json",
    "status",
    "validation_status",
    "readiness_status",
    "created_at",
    "sealed_at",
)

_BUNDLE_CHUNK_COLUMNS = (
    "embedding_bundle_id",
    "child_chunk_id",
    "parent_chunk_id",
    "document_id",
    "vector_offset",
    "vector_length",
    "vector_checksum",
    "content_hash",
    "chunk_ordinal",
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresIndexingTargetRepository:
    """Read ``indexing_targets``, the authority over physical vector tables."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, indexing_target_id: str) -> IndexingTarget:
        """Return one target or raise ``LookupError``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_TARGET_COLUMNS)} FROM indexing_targets"
                " WHERE indexing_target_id = %s",
                (indexing_target_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"indexing target not found: {indexing_target_id}")
        return IndexingTarget.model_validate(_row_to_mapping(row, _TARGET_COLUMNS))

    def list_targets(self) -> list[IndexingTarget]:
        """Return every registered target."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_TARGET_COLUMNS)} FROM indexing_targets"
                " ORDER BY indexing_target_id"
            )
            rows = cursor.fetchall()
        return [
            IndexingTarget.model_validate(_row_to_mapping(row, _TARGET_COLUMNS))
            for row in rows
        ]


class PostgresEmbeddingProfileRepository:
    """Read and promote durable profiles stored in ``indexing_profiles``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, profile_id: str) -> EmbeddingProfile:
        """Return one profile or raise ``EmbeddingProfileNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_PROFILE_COLUMNS)} FROM indexing_profiles"
                " WHERE profile_id = %s",
                (profile_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise EmbeddingProfileNotFound(f"embedding profile not found: {profile_id}")
        return _profile_from_row(row)

    def list_profiles(self) -> list[EmbeddingProfile]:
        """Return every registered profile, blocked ones included."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_PROFILE_COLUMNS)} FROM indexing_profiles"
                " ORDER BY profile_id"
            )
            rows = cursor.fetchall()
        return [_profile_from_row(row) for row in rows]

    def mark_verified(
        self,
        *,
        profile_id: str,
        configuration_fingerprint: str,
        model_revision: str,
        document_enabled: bool,
        query_enabled: bool,
    ) -> EmbeddingProfile:
        """Promote one profile in a single statement.

        ``compatibility_status`` and the enablement flags move together so the
        ``indexing_profiles_enablement_requires_verified_compatibility`` check is
        never transiently violated.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE indexing_profiles
                   SET compatibility_status = 'verified',
                       configuration_fingerprint = %s,
                       model_revision = %s,
                       document_enabled = %s,
                       query_enabled = %s
                 WHERE profile_id = %s
                """,
                (
                    configuration_fingerprint,
                    model_revision,
                    document_enabled,
                    query_enabled,
                    profile_id,
                ),
            )
        return self.get(profile_id)


def _profile_from_row(row: Mapping[str, object] | Sequence[object]) -> EmbeddingProfile:
    values = _row_to_mapping(row, _PROFILE_COLUMNS)
    return EmbeddingProfile.model_validate(
        {
            "profile_id": values["profile_id"],
            "ingestion_origin": values["ingestion_origin"],
            "chunking_version": values["chunking_version"],
            "provider": values["embedding_provider"],
            "model": values["embedding_model"],
            "model_revision": values["model_revision"],
            "dimension": values["embedding_dimension"],
            "normalization": values["normalization"],
            "distance_metric": values["distance_metric"],
            "configuration_fingerprint": values["configuration_fingerprint"],
            "semantic_config": _json_object(values["semantic_config_json"]),
            "vector_table": values["vector_table"],
            "metadata_schema_version": values["metadata_schema_version"],
            "config_hash": values["config_hash"],
            "default_indexing_target_id": values["default_indexing_target_id"],
            "active": values["active"],
            "document_enabled": values["document_enabled"],
            "query_enabled": values["query_enabled"],
            "compatibility_status": values["compatibility_status"],
            "deprecated_at": values["deprecated_at"],
        }
    )


class PostgresChunkBundleRepository:
    """Read the durable ``chunk_bundles`` ledger."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, chunk_bundle_id: str) -> ChunkBundleRef:
        """Return one chunk bundle or raise ``ChunkBundleNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_CHUNK_BUNDLE_COLUMNS)} FROM chunk_bundles"
                " WHERE chunk_bundle_id = %s",
                (chunk_bundle_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ChunkBundleNotFound(f"chunk bundle not found: {chunk_bundle_id}")
        return ChunkBundleRef.model_validate(_row_to_mapping(row, _CHUNK_BUNDLE_COLUMNS))

    def list_bundles(self) -> list[ChunkBundleRef]:
        """Return every registered chunk bundle."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_CHUNK_BUNDLE_COLUMNS)} FROM chunk_bundles"
                " ORDER BY chunk_bundle_id"
            )
            rows = cursor.fetchall()
        return [
            ChunkBundleRef.model_validate(_row_to_mapping(row, _CHUNK_BUNDLE_COLUMNS))
            for row in rows
        ]

    def ensure_registered(self, bundle: ChunkBundleRef) -> ChunkBundleRef:
        """Upsert one chunk bundle so embedding and indexing FKs remain valid."""

        self._ensure_source_document_registered(bundle)
        legacy_conflict = self._prepare_legacy_fingerprint_reconciliation(bundle)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chunk_bundles (
                    chunk_bundle_id, project_id, bundle_fingerprint, profile_id,
                    profile_fingerprint, corpus_version, source_document_id,
                    artifact_relpath, parent_count, child_count, status,
                    rag_variant_id, semantic_recipe_fingerprint
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_bundle_id) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    bundle_fingerprint = EXCLUDED.bundle_fingerprint,
                    profile_id = EXCLUDED.profile_id,
                    profile_fingerprint = EXCLUDED.profile_fingerprint,
                    corpus_version = EXCLUDED.corpus_version,
                    source_document_id = EXCLUDED.source_document_id,
                    artifact_relpath = EXCLUDED.artifact_relpath,
                    parent_count = EXCLUDED.parent_count,
                    child_count = EXCLUDED.child_count,
                    status = EXCLUDED.status,
                    rag_variant_id = EXCLUDED.rag_variant_id,
                    semantic_recipe_fingerprint = EXCLUDED.semantic_recipe_fingerprint
                """,
                (
                    bundle.chunk_bundle_id,
                    bundle.project_id,
                    bundle.bundle_fingerprint,
                    bundle.profile_id,
                    bundle.profile_fingerprint,
                    bundle.corpus_version,
                    bundle.source_document_id,
                    bundle.artifact_relpath,
                    bundle.parent_count,
                    bundle.child_count,
                    bundle.status,
                    bundle.rag_variant_id,
                    bundle.semantic_recipe_fingerprint,
                ),
            )
        if legacy_conflict is not None:
            self._finalize_legacy_fingerprint_reconciliation(bundle, legacy_conflict)
        return self.get(bundle.chunk_bundle_id)

    def _prepare_legacy_fingerprint_reconciliation(
        self,
        bundle: ChunkBundleRef,
    ) -> ChunkBundleRef | None:
        existing = self._find_by_bundle_fingerprint(bundle.bundle_fingerprint)
        if existing is None or existing.chunk_bundle_id == bundle.chunk_bundle_id:
            return None
        if not self._is_reconcilable_legacy_bundle(existing):
            return None
        temporary_fingerprint = (
            f"{existing.bundle_fingerprint}::replaced-by::{bundle.chunk_bundle_id}"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chunk_bundles
                   SET bundle_fingerprint = %s
                 WHERE chunk_bundle_id = %s
                   AND status = 'legacy_unverified'
                """,
                (temporary_fingerprint, existing.chunk_bundle_id),
            )
        return existing

    def _finalize_legacy_fingerprint_reconciliation(
        self,
        bundle: ChunkBundleRef,
        legacy_bundle: ChunkBundleRef,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE embedding_runs
                   SET source_chunk_bundle_id = %s
                 WHERE source_chunk_bundle_id = %s
                """,
                (bundle.chunk_bundle_id, legacy_bundle.chunk_bundle_id),
            )
            cursor.execute(
                """
                UPDATE indexing_run_documents
                   SET source_chunk_bundle_id = %s
                 WHERE source_chunk_bundle_id = %s
                """,
                (bundle.chunk_bundle_id, legacy_bundle.chunk_bundle_id),
            )
            cursor.execute(
                """
                UPDATE indexing_nodes
                   SET source_chunk_bundle_id = %s,
                       chunking_bundle_fingerprint = %s
                 WHERE source_chunk_bundle_id = %s
                """,
                (
                    bundle.chunk_bundle_id,
                    bundle.bundle_fingerprint,
                    legacy_bundle.chunk_bundle_id,
                ),
            )
            cursor.execute(
                """
                DELETE FROM embedding_bundles
                 WHERE source_chunk_bundle_id = %s
                   AND status = 'legacy_unverified'
                """,
                (legacy_bundle.chunk_bundle_id,),
            )
            cursor.execute(
                """
                DELETE FROM chunk_bundles
                 WHERE chunk_bundle_id = %s
                   AND status = 'legacy_unverified'
                """,
                (legacy_bundle.chunk_bundle_id,),
            )

    def _find_by_bundle_fingerprint(self, bundle_fingerprint: str) -> ChunkBundleRef | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_CHUNK_BUNDLE_COLUMNS)} FROM chunk_bundles"
                " WHERE bundle_fingerprint = %s",
                (bundle_fingerprint,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ChunkBundleRef.model_validate(_row_to_mapping(row, _CHUNK_BUNDLE_COLUMNS))

    def _is_reconcilable_legacy_bundle(self, bundle: ChunkBundleRef) -> bool:
        return bundle.status == "legacy_unverified" and bundle.chunk_bundle_id.startswith(
            "legacy-"
        )

    def _ensure_source_document_registered(self, bundle: ChunkBundleRef) -> None:
        source_relpath = (bundle.source_relpath or "").strip()
        source_hash = (bundle.source_hash or "").strip()
        if not source_relpath or not source_hash:
            return

        artifact_paths = ArtifactPaths.for_source(source_relpath)
        markdown_relpath = (bundle.normalized_relpath or "").strip() or artifact_paths.markdown
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO indexing_normalized_documents (
                    document_id, source_relpath, source_hash, ingestion_origin,
                    corpus_version, processing_status, markdown_relpath,
                    metadata_relpath, pages_relpath, tables_relpath, forms_relpath,
                    artifact_fingerprint, metadata
                )
                VALUES (%s, %s, %s, 'local', %s, 'processed', %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (document_id) DO NOTHING
                """,
                (
                    bundle.source_document_id,
                    source_relpath,
                    source_hash,
                    bundle.corpus_version,
                    markdown_relpath,
                    artifact_paths.metadata,
                    artifact_paths.pages,
                    artifact_paths.tables,
                    artifact_paths.forms,
                    bundle.bundle_fingerprint,
                    json.dumps(
                        {
                            "profile_id": bundle.profile_id,
                            "profile_fingerprint": bundle.profile_fingerprint,
                            "registration_origin": "embedding_chunk_bundle_backfill",
                        },
                        sort_keys=True,
                    ),
                ),
            )


class PostgresEmbeddingRunRepository:
    """Durable ``embedding_runs`` ledger with a transactional claim."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def create(self, run: EmbeddingRun) -> EmbeddingRun:
        """Insert a run; replays return the row already stored under the key."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO embedding_runs (
                    embedding_run_id, idempotency_key, request_fingerprint,
                    source_chunk_bundle_id, embedding_profile_id,
                    configuration_fingerprint, project_id, rag_variant_id,
                    rag_release_id, runtime_engine, runtime_mode,
                    engine_revision_observed, status, summary_json, warnings_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (idempotency_key, request_fingerprint) DO NOTHING
                """,
                (
                    run.embedding_run_id,
                    run.idempotency_key,
                    run.request_fingerprint,
                    run.source_chunk_bundle_id,
                    run.embedding_profile_id,
                    run.configuration_fingerprint,
                    run.project_id,
                    run.rag_variant_id,
                    run.rag_release_id,
                    run.runtime_engine,
                    run.runtime_mode,
                    run.engine_revision_observed,
                    run.status,
                    json.dumps(run.summary, sort_keys=True),
                    json.dumps(run.warnings),
                ),
            )
        return self.get(run.embedding_run_id)

    def get(self, embedding_run_id: str) -> EmbeddingRun:
        """Return one run or raise ``EmbeddingRunNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM embedding_runs"
                " WHERE embedding_run_id = %s",
                (embedding_run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise EmbeddingRunNotFound(f"embedding run not found: {embedding_run_id}")
        return _run_from_row(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> EmbeddingRun | None:
        """Return the run stored under one idempotency key."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM embedding_runs"
                " WHERE idempotency_key = %s ORDER BY created_at DESC LIMIT 1",
                (idempotency_key,),
            )
            row = cursor.fetchone()
        return None if row is None else _run_from_row(row)

    def list_runs(self) -> list[EmbeddingRun]:
        """Return every run, newest first."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RUN_COLUMNS)} FROM embedding_runs"
                " ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
        return [_run_from_row(row) for row in rows]

    def claim(self, embedding_run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once.

        The conditional ``UPDATE`` is the claim: a second worker sees zero
        affected rows and gives up instead of running the same bundle twice.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE embedding_runs
                   SET status = 'running', started_at = now()
                 WHERE embedding_run_id = %s AND status = 'pending'
                """,
                (embedding_run_id,),
            )
            return int(cursor.rowcount) == 1

    def update(self, run: EmbeddingRun) -> EmbeddingRun:
        """Persist a durable state transition."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE embedding_runs
                   SET status = %s,
                       engine_revision_observed = %s,
                       completed_at = %s,
                       summary_json = %s::jsonb,
                       warnings_json = %s::jsonb,
                       error_summary = %s,
                       produced_embedding_bundle_id = %s
                 WHERE embedding_run_id = %s
                """,
                (
                    run.status,
                    run.engine_revision_observed,
                    run.completed_at,
                    json.dumps(run.summary, sort_keys=True, default=str),
                    json.dumps(run.warnings),
                    run.error_summary,
                    run.produced_embedding_bundle_id,
                    run.embedding_run_id,
                ),
            )
        return self.get(run.embedding_run_id)

    def reconcile_interrupted(self) -> list[str]:
        """Fail runs left ``running`` by a process that never finished."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE embedding_runs
                   SET status = 'failed',
                       error_summary = 'EMBEDDING_RUN_INTERRUPTED',
                       completed_at = now()
                 WHERE status = 'running'
                RETURNING embedding_run_id
                """
            )
            rows = cursor.fetchall()
        return [str(row[0] if not isinstance(row, Mapping) else row["embedding_run_id"]) for row in rows]


def _run_from_row(row: Mapping[str, object] | Sequence[object]) -> EmbeddingRun:
    values = _row_to_mapping(row, _RUN_COLUMNS)
    return EmbeddingRun.model_validate(
        {
            "embedding_run_id": values["embedding_run_id"],
            "idempotency_key": values["idempotency_key"],
            "request_fingerprint": values["request_fingerprint"],
            "source_chunk_bundle_id": values["source_chunk_bundle_id"],
            "embedding_profile_id": values["embedding_profile_id"],
            "configuration_fingerprint": values["configuration_fingerprint"],
            "project_id": values["project_id"],
            "rag_variant_id": values["rag_variant_id"],
            "rag_release_id": values["rag_release_id"],
            "runtime_engine": values["runtime_engine"],
            "runtime_mode": values["runtime_mode"],
            "engine_revision_observed": values["engine_revision_observed"],
            "status": values["status"],
            "started_at": values["started_at"],
            "completed_at": values["completed_at"],
            "summary": _json_object(values["summary_json"]),
            "warnings": _json_list(values["warnings_json"]),
            "error_summary": values["error_summary"],
            "produced_embedding_bundle_id": values["produced_embedding_bundle_id"],
            "created_at": values["created_at"],
        }
    )


class PostgresEmbeddingBundleRepository:
    """Durable ``embedding_bundles`` and ``embedding_bundle_chunks`` ledger."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def upsert(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Insert or update a bundle that is not sealed yet."""

        self._reject_if_sealed(bundle.embedding_bundle_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO embedding_bundles (
                    embedding_bundle_id, project_id, source_chunk_bundle_id,
                    embedding_profile_id,
                    provider, model, model_revision, dimension, normalization,
                    distance_metric, configuration_fingerprint, corpus_version,
                    semantic_config_json, bundle_schema_version,
                    source_content_fingerprint, vector_artifact_relpath,
                    chunk_map_relpath, vector_dtype, vector_shape, vector_count,
                    checksums_json, status, validation_status, readiness_status,
                    sealed_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s,
                    %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s
                )
                ON CONFLICT (embedding_bundle_id) DO UPDATE SET
                    vector_artifact_relpath = EXCLUDED.vector_artifact_relpath,
                    chunk_map_relpath = EXCLUDED.chunk_map_relpath,
                    vector_dtype = EXCLUDED.vector_dtype,
                    vector_shape = EXCLUDED.vector_shape,
                    vector_count = EXCLUDED.vector_count,
                    checksums_json = EXCLUDED.checksums_json,
                    status = EXCLUDED.status,
                    validation_status = EXCLUDED.validation_status,
                    readiness_status = EXCLUDED.readiness_status,
                    sealed_at = EXCLUDED.sealed_at
                """,
                _bundle_parameters(bundle),
            )
        return self.get(bundle.embedding_bundle_id)

    def seal(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Persist the sealed bundle; the SQL check enforces completeness."""

        return self.upsert(bundle)

    def get(self, embedding_bundle_id: str) -> EmbeddingBundle:
        """Return one bundle or raise ``EmbeddingBundleNotFound``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_BUNDLE_COLUMNS)} FROM embedding_bundles"
                " WHERE embedding_bundle_id = %s",
                (embedding_bundle_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise EmbeddingBundleNotFound(
                f"embedding bundle not found: {embedding_bundle_id}"
            )
        return _bundle_from_row(row)

    def find_by_identity(
        self,
        *,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
        corpus_version: str,
        source_content_fingerprint: str,
        bundle_schema_version: str,
    ) -> EmbeddingBundle | None:
        """Return an existing bundle for the deterministic identity tuple."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {', '.join(_BUNDLE_COLUMNS)} FROM embedding_bundles
                 WHERE source_chunk_bundle_id = %s
                   AND embedding_profile_id = %s
                   AND configuration_fingerprint = %s
                   AND corpus_version = %s
                   AND source_content_fingerprint = %s
                   AND bundle_schema_version = %s
                """,
                (
                    source_chunk_bundle_id,
                    embedding_profile_id,
                    configuration_fingerprint,
                    corpus_version,
                    source_content_fingerprint,
                    bundle_schema_version,
                ),
            )
            row = cursor.fetchone()
        return None if row is None else _bundle_from_row(row)

    def replace_chunks(
        self,
        *,
        embedding_bundle_id: str,
        chunks: Sequence[EmbeddingBundleChunk],
    ) -> int:
        """Replace the chunk map rows of one unsealed bundle."""

        self._reject_if_sealed(embedding_bundle_id)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM embedding_bundle_chunks WHERE embedding_bundle_id = %s",
                (embedding_bundle_id,),
            )
            for chunk in chunks:
                cursor.execute(
                    """
                    INSERT INTO embedding_bundle_chunks (
                        embedding_bundle_id, child_chunk_id, parent_chunk_id,
                        document_id, vector_offset, vector_length, vector_checksum,
                        content_hash, chunk_ordinal
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk.embedding_bundle_id,
                        chunk.child_chunk_id,
                        chunk.parent_chunk_id,
                        chunk.document_id,
                        chunk.vector_offset,
                        chunk.vector_length,
                        chunk.vector_checksum,
                        chunk.content_hash,
                        chunk.chunk_ordinal,
                    ),
                )
        return len(chunks)

    def list_chunks(self, embedding_bundle_id: str) -> list[EmbeddingBundleChunk]:
        """Return the durable chunk map ordered by ``chunk_ordinal``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_BUNDLE_CHUNK_COLUMNS)} FROM embedding_bundle_chunks"
                " WHERE embedding_bundle_id = %s ORDER BY chunk_ordinal",
                (embedding_bundle_id,),
            )
            rows = cursor.fetchall()
        return [
            EmbeddingBundleChunk.model_validate(
                _row_to_mapping(row, _BUNDLE_CHUNK_COLUMNS)
            )
            for row in rows
        ]

    def set_readiness_status(
        self,
        *,
        embedding_bundle_id: str,
        readiness_status: str,
    ) -> EmbeddingBundle:
        """Update the operational readiness projection of a sealed bundle."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE embedding_bundles SET readiness_status = %s"
                " WHERE embedding_bundle_id = %s",
                (readiness_status, embedding_bundle_id),
            )
        return self.get(embedding_bundle_id)

    def _reject_if_sealed(self, embedding_bundle_id: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM embedding_bundles WHERE embedding_bundle_id = %s",
                (embedding_bundle_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return
        status = row["status"] if isinstance(row, Mapping) else row[0]
        if status == "sealed":
            raise EmbeddingBundleInvalid("cannot modify a sealed embedding bundle")


def _bundle_parameters(bundle: EmbeddingBundle) -> tuple[object, ...]:
    return (
        bundle.embedding_bundle_id,
        bundle.project_id,
        bundle.source_chunk_bundle_id,
        bundle.embedding_profile_id,
        bundle.provider,
        bundle.model,
        bundle.model_revision,
        bundle.dimension,
        bundle.normalization,
        bundle.distance_metric,
        bundle.configuration_fingerprint,
        bundle.corpus_version,
        json.dumps(bundle.semantic_config, sort_keys=True),
        bundle.bundle_schema_version,
        bundle.source_content_fingerprint,
        bundle.vector_artifact_relpath,
        bundle.chunk_map_relpath,
        bundle.vector_dtype,
        bundle.vector_shape,
        bundle.vector_count,
        json.dumps(bundle.checksums, sort_keys=True),
        bundle.status,
        bundle.validation_status,
        bundle.readiness_status,
        bundle.sealed_at,
    )


def _bundle_from_row(row: Mapping[str, object] | Sequence[object]) -> EmbeddingBundle:
    values = _row_to_mapping(row, _BUNDLE_COLUMNS)
    return EmbeddingBundle.model_validate(
        {
            **{
                key: values[key]
                for key in _BUNDLE_COLUMNS
                if key not in {"semantic_config_json", "checksums_json"}
            },
            "semantic_config": _json_object(values["semantic_config_json"]),
            "checksums": {
                str(key): str(value)
                for key, value in _json_object(values["checksums_json"]).items()
            },
        }
    )


class PostgresReadinessCheckRepository:
    """Append-only ``readiness_checks`` ledger."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def record(self, check: ReadinessCheck) -> ReadinessCheck:
        """Persist one readiness check idempotently."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO readiness_checks (
                    check_id, check_kind, subject_id, embedding_profile_id,
                    indexing_target_id, status, validator_version, report_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (check_id) DO NOTHING
                """,
                (
                    check.check_id,
                    check.check_kind,
                    check.subject_id,
                    check.embedding_profile_id,
                    check.indexing_target_id,
                    check.status,
                    check.validator_version,
                    json.dumps(check.report, sort_keys=True, default=str),
                ),
            )
        return check.model_copy(update={"created_at": check.created_at or _now()})

    def latest(self, *, check_kind: str, subject_id: str) -> ReadinessCheck | None:
        """Return the most recent check for one subject."""

        columns = (
            "check_id",
            "check_kind",
            "subject_id",
            "embedding_profile_id",
            "indexing_target_id",
            "status",
            "validator_version",
            "report_json",
            "created_at",
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(columns)} FROM readiness_checks"
                " WHERE check_kind = %s AND subject_id = %s"
                " ORDER BY created_at DESC LIMIT 1",
                (check_kind, subject_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        values = _row_to_mapping(row, columns)
        return ReadinessCheck.model_validate(
            {
                **{key: values[key] for key in columns if key != "report_json"},
                "report": _json_object(values["report_json"]),
            }
        )
