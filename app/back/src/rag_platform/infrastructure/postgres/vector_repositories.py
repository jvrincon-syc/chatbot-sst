"""Adaptadores PostgreSQL de materialización de vectores y embeddings (Fase 4).

Reflejan el esquema añadido por las migraciones ``20260810_05``/``20260810_06``
(aditivas sobre legacy) y **nunca** emiten DDL. No se ejecutan en unit tests (se
prueban con fakes in-memory que reproducen el contrato observable); aquí se refleja
el SQL para el entorno real.

- ``PostgresIndexingMaterializationRepository``: lifecycle inmutable
  ``WRITING → SEALED | FAILED`` sobre ``indexing_materializations`` (ADR-007 §3).
  Nunca ``upsert`` sobre una fila sellada.
- ``PostgresSealedEmbeddingBundleRepository``: consulta de embedding bundles sellados
  por identidad física exacta scoped por ``project_id`` (cierra deuda Fase 3-b).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import uuid

from rag_platform.domain.errors import MaterializationSealed
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    IndexingMaterialization,
    MaterializationStatus,
    PhysicalDistanceMetric,
    SealedEmbeddingBundle,
    SealingStatus,
)


#: Columnas de ``indexing_materializations`` en orden de proyección.
_MATERIALIZATION_COLUMNS = (
    "materialization_id",
    "project_id",
    "embedding_bundle_id",
    "indexing_target_id",
    "storage_schema_version",
    "status",
    "canonical_checksum",
    "parent_node_count",
    "child_node_count",
    "vector_count",
    "started_at",
    "sealed_at",
    "failed_at",
    "failure_code",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


class PostgresIndexingMaterializationRepository:
    """Repositorio del lifecycle inmutable de materializaciones (ADR-007 §3)."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization | None:
        """Devuelve la materialización ``SEALED`` con esa identidad, o ``None``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_MATERIALIZATION_COLUMNS)}"
                " FROM indexing_materializations"
                " WHERE project_id = %s AND embedding_bundle_id = %s"
                "   AND indexing_target_id = %s AND storage_schema_version = %s"
                "   AND status = %s",
                (
                    project_id.value,
                    embedding_bundle_id,
                    indexing_target_id,
                    storage_schema_version,
                    MaterializationStatus.SEALED.value,
                ),
            )
            row = cursor.fetchone()
        return None if row is None else self._row_to_model(row)

    def begin_writing(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization:
        """Abre una materialización ``WRITING`` (idempotente por identidad)."""

        materialization_id = f"mat_{uuid.uuid4().hex}"
        started_at = _now()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO indexing_materializations (
                    materialization_id, project_id, embedding_bundle_id,
                    indexing_target_id, storage_schema_version, status, started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    project_id, embedding_bundle_id, indexing_target_id,
                    storage_schema_version
                ) DO UPDATE SET
                    status = EXCLUDED.status,
                    started_at = EXCLUDED.started_at,
                    sealed_at = NULL,
                    failed_at = NULL,
                    failure_code = NULL,
                    canonical_checksum = NULL
                WHERE indexing_materializations.status <> %s
                RETURNING materialization_id, started_at
                """,
                (
                    materialization_id,
                    project_id.value,
                    embedding_bundle_id,
                    indexing_target_id,
                    storage_schema_version,
                    MaterializationStatus.WRITING.value,
                    started_at,
                    MaterializationStatus.SEALED.value,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            # El WHERE bloqueó el UPDATE: ya existe una fila SEALED (inmutable).
            raise MaterializationSealed(
                "materialization is already sealed and cannot be reopened for writing"
            )
        return IndexingMaterialization(
            materialization_id=str(row[0]),
            project_id=project_id,
            embedding_bundle_id=embedding_bundle_id,
            indexing_target_id=indexing_target_id,
            storage_schema_version=storage_schema_version,
            status=MaterializationStatus.WRITING,
            started_at=row[1],  # type: ignore[arg-type]
        )

    def seal(
        self,
        *,
        materialization_id: str,
        canonical_checksum: str,
        parent_node_count: int,
        child_node_count: int,
        vector_count: int,
    ) -> IndexingMaterialization:
        """Sella una materialización ``WRITING``; nunca re-sella una ``SEALED``."""

        sealed_at = _now()
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE indexing_materializations
                   SET status = %s,
                       canonical_checksum = %s,
                       parent_node_count = %s,
                       child_node_count = %s,
                       vector_count = %s,
                       sealed_at = %s
                 WHERE materialization_id = %s AND status = %s
                RETURNING {', '.join(_MATERIALIZATION_COLUMNS)}
                """,
                (
                    MaterializationStatus.SEALED.value,
                    canonical_checksum,
                    parent_node_count,
                    child_node_count,
                    vector_count,
                    sealed_at,
                    materialization_id,
                    MaterializationStatus.WRITING.value,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise MaterializationSealed(
                f"materialization {materialization_id!r} is not in WRITING state"
            )
        return self._row_to_model(row)

    def mark_failed(
        self, *, materialization_id: str, failure_code: str
    ) -> IndexingMaterialization:
        """Marca una materialización ``WRITING`` como ``FAILED`` (observable)."""

        failed_at = _now()
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE indexing_materializations
                   SET status = %s, failed_at = %s, failure_code = %s
                 WHERE materialization_id = %s AND status = %s
                RETURNING {', '.join(_MATERIALIZATION_COLUMNS)}
                """,
                (
                    MaterializationStatus.FAILED.value,
                    failed_at,
                    failure_code,
                    materialization_id,
                    MaterializationStatus.WRITING.value,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise MaterializationSealed(
                f"materialization {materialization_id!r} is not in WRITING state"
            )
        return self._row_to_model(row)

    @staticmethod
    def _row_to_model(row: Sequence[object]) -> IndexingMaterialization:
        return IndexingMaterialization(
            materialization_id=str(row[0]),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            embedding_bundle_id=str(row[2]),
            indexing_target_id=str(row[3]),
            storage_schema_version=str(row[4]),
            status=MaterializationStatus(str(row[5])),
            canonical_checksum=None if row[6] is None else str(row[6]),
            parent_node_count=int(row[7]),  # type: ignore[arg-type]
            child_node_count=int(row[8]),  # type: ignore[arg-type]
            vector_count=int(row[9]),  # type: ignore[arg-type]
            started_at=row[10],  # type: ignore[arg-type]
            sealed_at=row[11],  # type: ignore[arg-type]
            failed_at=row[12],  # type: ignore[arg-type]
            failure_code=None if row[13] is None else str(row[13]),
        )


class PostgresSealedEmbeddingBundleRepository:
    """Consulta embedding bundles sellados de plataforma por identidad exacta.

    La identidad incluye ``project_id``; un bundle de otro proyecto nunca coincide,
    aunque su contenido sea idéntico (fail-closed, cierra deuda Fase 3-b).
    """

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
    ) -> SealedEmbeddingBundle | None:
        """Devuelve el embedding bundle sellado con esa identidad, o ``None``."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT embedding_bundle_id, source_chunk_bundle_id, dimension,
                       distance_metric, vector_count, checksums_json
                FROM embedding_bundles
                WHERE project_id = %s
                  AND source_chunk_bundle_id = %s
                  AND embedding_profile_id = %s
                  AND configuration_fingerprint = %s
                  AND status = %s
                """,
                (
                    project_id.value,
                    source_chunk_bundle_id,
                    embedding_profile_id,
                    configuration_fingerprint,
                    "sealed",
                ),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        checksums = {str(k): str(v) for k, v in dict(row[5] or {}).items()}  # type: ignore[arg-type]
        return SealedEmbeddingBundle(
            embedding_bundle_id=str(row[0]),
            project_id=project_id,
            source_chunk_bundle_id=str(row[1]),
            bundle_dir_relpath=f"embeddings/{row[0]}",
            checksums=checksums,
            dimension=int(row[2]),  # type: ignore[arg-type]
            distance_metric=_as_metric(str(row[3])),
            vector_count=int(row[4]),  # type: ignore[arg-type]
            sealing_status=SealingStatus.SEALED,
        )


def _as_metric(value: str) -> PhysicalDistanceMetric:
    if value not in ("cosine", "l2", "inner_product"):
        raise ValueError(f"unknown distance metric read from db: {value!r}")
    return value  # type: ignore[return-value]
