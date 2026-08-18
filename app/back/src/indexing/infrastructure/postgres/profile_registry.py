from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from indexing.domain.bundle_first import IndexingTarget
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from psycopg2 import sql


class ProfileNotFoundError(LookupError):
    """Raised when an indexing profile is missing from the registry."""


class IndexingTargetReader(Protocol):
    """Minimal read port over the durable indexing target catalog."""

    def get(self, indexing_target_id: str) -> IndexingTarget:
        """Return one target or fail closed."""


class InMemoryProfileRegistry:
    """Deterministic profile registry for tests and dry-run wiring."""

    def __init__(self, profiles: Iterable[ResolvedIndexingProfile]) -> None:
        self._profiles = {profile.profile_id: profile for profile in profiles}

    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        """Return an immutable profile or fail closed."""

        try:
            return self._profiles[profile_id]
        except KeyError as error:
            raise ProfileNotFoundError(f"indexing profile not found: {profile_id}") from error


class PostgresProfileRegistry:
    """PostgreSQL-backed profile registry adapter."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        """Read one profile using a parameterized query."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT profile_id, ingestion_origin, chunking_version,
                       embedding_provider, embedding_model, embedding_dimension,
                       distance_metric, vector_table, metadata_schema_version,
                       active, config_hash
                  FROM indexing_profiles
                 WHERE profile_id = %s
                """,
                (profile_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ProfileNotFoundError(f"indexing profile not found: {profile_id}")
        return _profile_from_row(row)


def safe_vector_table_identifier(
    *,
    profile_id: str,
    indexing_target_id: str,
    registry: "PostgresProfileRegistry | InMemoryProfileRegistry",
    targets: IndexingTargetReader,
) -> sql.Identifier:
    """Return the trusted physical vector table identifier for bundle-first writes."""

    profile = registry.get(profile_id)
    target = targets.get(indexing_target_id)
    if target.vector_table != profile.vector_table:
        raise VectorStoreWriteError("indexing target/catalog table mismatch")
    return sql.Identifier(target.postgres_schema, target.vector_table)


def _profile_from_row(row: Mapping[str, object] | tuple[object, ...]) -> ResolvedIndexingProfile:
    if isinstance(row, Mapping):
        values = row
    else:
        keys = (
            "profile_id",
            "ingestion_origin",
            "chunking_version",
            "embedding_provider",
            "embedding_model",
            "embedding_dimension",
            "distance_metric",
            "vector_table",
            "metadata_schema_version",
            "active",
            "config_hash",
        )
        values = dict(zip(keys, row))
    return ResolvedIndexingProfile.model_validate(values)
