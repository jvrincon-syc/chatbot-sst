"""PostgreSQL adapters for the RAG platform catalog (Fase 1).

Every statement is parameterized and every table already exists: this module
reflects the schema frozen by migration ``20260810_01`` and never issues DDL,
mirroring the pattern of ``embedding/infrastructure/postgres/repositories.py``.
Credentials are never read from or written to the database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json

from rag_platform.domain.errors import (
    ChunkingProfileNotFound,
    DuplicateVariantRecipe,
    ProcessingProfileNotFound,
    ProjectAlreadyExists,
    ProjectNotFound,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    CorpusOrganizationPolicy,
    DocumentProcessingProfile,
    ProcessingOrigin,
    ProfileVerificationStatus,
    ProjectConfiguration,
    ProjectDocumentType,
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
    ProjectStorageRoots,
    RagProject,
    RagVariant,
    RagVariantState,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, (str, bytes)):
        return dict(json.loads(value))
    return dict(value)  # type: ignore[arg-type]


class PostgresProjectRepository:
    """Reads and writes ``rag_projects`` and its versioned configuration."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def exists(self, project_id: PlatformId) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM rag_projects WHERE project_id = %s",
                (project_id.value,),
            )
            return cursor.fetchone() is not None

    def get(self, project_id: PlatformId) -> RagProject:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT project_id, display_name, state, storage_root_raw,"
                " storage_root_normalized, storage_root_chunks,"
                " storage_root_embeddings, storage_root_manifests, created_at"
                " FROM rag_projects WHERE project_id = %s",
                (project_id.value,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ProjectNotFound(project_id.value)
            configuration = self._load_configuration(cursor, project_id.value)
        return self._row_to_project(row, configuration)

    def has_documents(self, project_id: PlatformId) -> bool:
        # Fase 1 has no project_documents table yet; the projection lands in
        # Fase 2. Until then no project owns documents.
        # ponytail: returns False until 20260810_02 adds project_documents.
        return False

    def add(self, project: RagProject) -> RagProject:
        roots = project.storage_roots
        config = project.configuration
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO rag_projects (project_id, display_name, state,"
                    " storage_root_raw, storage_root_normalized, storage_root_chunks,"
                    " storage_root_embeddings, storage_root_manifests, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        project.project_id.value,
                        project.display_name,
                        project.state.value,
                        roots.raw,
                        roots.normalized,
                        roots.chunks,
                        roots.embeddings,
                        roots.manifests,
                        project.created_at,
                    ),
                )
                cursor.execute(
                    "INSERT INTO project_configuration_versions"
                    " (project_id, version, corpus_organization_policy, created_at)"
                    " VALUES (%s, %s, %s, %s)",
                    (
                        project.project_id.value,
                        config.version,
                        config.corpus_organization_policy.value,
                        config.created_at,
                    ),
                )
                for doc_type in config.document_types:
                    cursor.execute(
                        "INSERT INTO project_document_types"
                        " (project_id, configuration_version, code, display_name, template)"
                        " VALUES (%s, %s, %s, %s, %s)",
                        (
                            project.project_id.value,
                            config.version,
                            doc_type.code,
                            doc_type.display_name,
                            doc_type.template.value,
                        ),
                    )
                for emb in config.embedding_profiles:
                    cursor.execute(
                        "INSERT INTO project_embedding_profiles"
                        " (project_id, configuration_version, embedding_profile_id, enabled)"
                        " VALUES (%s, %s, %s, %s)",
                        (
                            project.project_id.value,
                            config.version,
                            emb.embedding_profile_id,
                            emb.enabled,
                        ),
                    )
                for binding in config.target_bindings:
                    cursor.execute(
                        "INSERT INTO project_indexing_target_bindings"
                        " (project_id, binding_key, indexing_target_id, embedding_profile_id)"
                        " VALUES (%s, %s, %s, %s)",
                        (
                            project.project_id.value,
                            binding.binding_key,
                            binding.indexing_target_id,
                            binding.embedding_profile_id,
                        ),
                    )
        except Exception as error:  # noqa: BLE001 - integration boundary
            # A unique violation on the primary key means the project exists.
            if _is_unique_violation(error):
                raise ProjectAlreadyExists(project.project_id.value) from error
            raise
        return project

    def _load_configuration(
        self, cursor: object, project_id_value: str
    ) -> ProjectConfiguration:
        cursor.execute(
            "SELECT version, corpus_organization_policy, created_at"
            " FROM project_configuration_versions"
            " WHERE project_id = %s ORDER BY version DESC LIMIT 1",
            (project_id_value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ProjectNotFound(project_id_value)
        version, policy, created_at = row[0], row[1], row[2]
        cursor.execute(
            "SELECT code, display_name, template FROM project_document_types"
            " WHERE project_id = %s AND configuration_version = %s ORDER BY code",
            (project_id_value, version),
        )
        document_types = tuple(
            ProjectDocumentType(code=r[0], display_name=r[1], template=r[2])
            for r in cursor.fetchall()
        )
        cursor.execute(
            "SELECT embedding_profile_id, enabled FROM project_embedding_profiles"
            " WHERE project_id = %s AND configuration_version = %s"
            " ORDER BY embedding_profile_id",
            (project_id_value, version),
        )
        embedding_profiles = tuple(
            ProjectEmbeddingProfile(embedding_profile_id=r[0], enabled=r[1])
            for r in cursor.fetchall()
        )
        cursor.execute(
            "SELECT binding_key, indexing_target_id, embedding_profile_id"
            " FROM project_indexing_target_bindings"
            " WHERE project_id = %s ORDER BY binding_key",
            (project_id_value,),
        )
        target_bindings = tuple(
            ProjectIndexingTargetBinding(
                binding_key=r[0], indexing_target_id=r[1], embedding_profile_id=r[2]
            )
            for r in cursor.fetchall()
        )
        return ProjectConfiguration(
            version=version,
            document_types=document_types,
            embedding_profiles=embedding_profiles,
            target_bindings=target_bindings,
            corpus_organization_policy=CorpusOrganizationPolicy(policy),
            created_at=created_at,
        )

    @staticmethod
    def _row_to_project(
        row: Sequence[object], configuration: ProjectConfiguration
    ) -> RagProject:
        project_id = _pid(IdentityKind.PROJECT, str(row[0]))
        return RagProject(
            project_id=project_id,
            display_name=str(row[1]),
            state=str(row[2]),  # type: ignore[arg-type]
            storage_roots=ProjectStorageRoots(
                project_id=project_id,
                raw=str(row[3]),
                normalized=str(row[4]),
                chunks=str(row[5]),
                embeddings=str(row[6]),
                manifests=str(row[7]),
            ),
            configuration=configuration,
            created_at=row[8],  # type: ignore[arg-type]
        )


class PostgresProcessingProfileRepository:
    """Reads ``document_processing_profiles``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, processing_profile_id: PlatformId) -> DocumentProcessingProfile:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT processing_profile_id, project_id, provider, engine,"
                " observed_revision, origin, sanitized_config_json, fingerprint,"
                " status, created_at FROM document_processing_profiles"
                " WHERE processing_profile_id = %s",
                (processing_profile_id.value,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ProcessingProfileNotFound(processing_profile_id.value)
        return DocumentProcessingProfile(
            processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE, str(row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            provider=str(row[2]),
            engine=str(row[3]),
            observed_revision=str(row[4]),
            origin=ProcessingOrigin(str(row[5])),
            sanitized_config=_json_object(row[6]),
            fingerprint=str(row[7]),
            status=ProfileVerificationStatus(str(row[8])),
            created_at=row[9],  # type: ignore[arg-type]
        )


class PostgresChunkingProfileRepository:
    """Reads ``chunking_profiles``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, chunking_profile_id: PlatformId) -> ChunkingProfile:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT chunking_profile_id, project_id, strategy,"
                " sanitized_config_json, fingerprint, status, created_at"
                " FROM chunking_profiles WHERE chunking_profile_id = %s",
                (chunking_profile_id.value,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ChunkingProfileNotFound(chunking_profile_id.value)
        return ChunkingProfile(
            chunking_profile_id=_pid(IdentityKind.CHUNKING_PROFILE, str(row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            strategy=str(row[2]),
            sanitized_config=_json_object(row[3]),
            fingerprint=str(row[4]),
            status=ProfileVerificationStatus(str(row[5])),
            created_at=row[6],  # type: ignore[arg-type]
        )


class PostgresRagVariantRepository:
    """Reads and writes ``rag_variants`` with active-recipe uniqueness."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_active_by_fingerprint(
        self, project_id: PlatformId, semantic_recipe_fingerprint: str
    ) -> RagVariant | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT rag_variant_id, project_id, processing_profile_id,"
                " chunking_profile_id, embedding_profile_id,"
                " semantic_recipe_fingerprint, state, created_at FROM rag_variants"
                " WHERE project_id = %s AND semantic_recipe_fingerprint = %s"
                " AND state = 'active'",
                (project_id.value, semantic_recipe_fingerprint),
            )
            row = cursor.fetchone()
        return None if row is None else self._row_to_variant(row)

    def add(self, variant: RagVariant) -> RagVariant:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO rag_variants (rag_variant_id, project_id,"
                    " processing_profile_id, chunking_profile_id, embedding_profile_id,"
                    " semantic_recipe_fingerprint, state, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        variant.rag_variant_id.value,
                        variant.project_id.value,
                        variant.processing_profile_id.value,
                        variant.chunking_profile_id.value,
                        variant.embedding_profile_id,
                        variant.semantic_recipe_fingerprint,
                        variant.state.value,
                        variant.created_at,
                    ),
                )
        except Exception as error:  # noqa: BLE001 - integration boundary
            if _is_unique_violation(error):
                raise DuplicateVariantRecipe(
                    variant.semantic_recipe_fingerprint
                ) from error
            raise
        return variant

    @staticmethod
    def _row_to_variant(row: Sequence[object]) -> RagVariant:
        return RagVariant(
            rag_variant_id=_pid(IdentityKind.RAG_VARIANT, str(row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            processing_profile_id=_pid(IdentityKind.PROCESSING_PROFILE, str(row[2])),
            chunking_profile_id=_pid(IdentityKind.CHUNKING_PROFILE, str(row[3])),
            embedding_profile_id=str(row[4]),
            semantic_recipe_fingerprint=str(row[5]),
            state=RagVariantState(str(row[6])),
            created_at=row[7],  # type: ignore[arg-type]
        )


class PostgresTargetBindingResolver:
    """Reads the ``project_indexing_target_bindings`` allowlist."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_binding(
        self, project_id: PlatformId, binding_key: str
    ) -> ProjectIndexingTargetBinding | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT binding_key, indexing_target_id, embedding_profile_id"
                " FROM project_indexing_target_bindings"
                " WHERE project_id = %s AND binding_key = %s",
                (project_id.value, binding_key),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ProjectIndexingTargetBinding(
            binding_key=str(row[0]),
            indexing_target_id=str(row[1]),
            embedding_profile_id=str(row[2]),
        )


def _is_unique_violation(error: Exception) -> bool:
    """Best-effort detection of a PostgreSQL unique-violation (SQLSTATE 23505).

    psycopg exposes ``error.sqlstate``/``error.pgcode``; falling back to the
    class name keeps this driver-agnostic without importing the SDK here.
    """

    sqlstate = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
    if sqlstate == "23505":
        return True
    return type(error).__name__ == "UniqueViolation"
