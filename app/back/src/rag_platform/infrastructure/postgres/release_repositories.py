"""PostgreSQL adapters for releases and memberships (Fase 5).

Reflects the schema frozen by migration ``20260810_07`` and never issues DDL,
mirroring the pattern of ``project_repositories.py``. Every statement is
parameterized. Credentials are never read from or written to the database.
"""

from __future__ import annotations

from datetime import datetime

from rag_platform.domain.errors import RagReleaseNotFound
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import (
    RagRelease,
    RagReleaseMembership,
    ReleaseState,
)

_RELEASE_COLUMNS = (
    "rag_release_id",
    "project_id",
    "rag_variant_id",
    "corpus_snapshot_id",
    "target_binding_key",
    "release_number",
    "state",
    "release_manifest_hash",
    "created_by",
    "created_at",
    "validated_at",
    "reason",
)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


class PostgresRagReleaseRepository:
    """Reads and writes ``rag_releases``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def add(self, release: RagRelease) -> RagRelease:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rag_releases ("
                " rag_release_id, project_id, rag_variant_id, corpus_snapshot_id,"
                " target_binding_key, release_number, state, release_manifest_hash,"
                " created_by, created_at, validated_at, reason)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    release.rag_release_id.value,
                    release.project_id.value,
                    release.rag_variant_id.value,
                    release.corpus_snapshot_id.value,
                    release.target_binding_key,
                    release.release_number,
                    release.state.value,
                    release.release_manifest_hash,
                    release.created_by,
                    release.created_at,
                    release.validated_at,
                    release.reason,
                ),
            )
        return release

    def get(self, rag_release_id: PlatformId) -> RagRelease:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(_RELEASE_COLUMNS)} FROM rag_releases"
                " WHERE rag_release_id = %s",
                (rag_release_id.value,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RagReleaseNotFound(rag_release_id.value)
        return _row_to_release(row)

    def list_release_numbers(self, rag_variant_id: PlatformId) -> list[int]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT release_number FROM rag_releases WHERE rag_variant_id = %s",
                (rag_variant_id.value,),
            )
            return [int(row[0]) for row in cursor.fetchall()]

    def update_state(
        self,
        *,
        rag_release_id: PlatformId,
        state: ReleaseState,
        release_manifest_hash: str | None = None,
        validated_at: datetime | None = None,
        reason: str | None = None,
    ) -> RagRelease:
        # COALESCE preserva el valor actual cuando el parámetro es NULL (no borra el
        # manifiesto ni la fecha ya congelados en una transición posterior).
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE rag_releases SET state = %s,"
                " release_manifest_hash = COALESCE(%s, release_manifest_hash),"
                " validated_at = COALESCE(%s, validated_at),"
                " reason = COALESCE(%s, reason)"
                " WHERE rag_release_id = %s",
                (
                    state.value,
                    release_manifest_hash,
                    validated_at,
                    reason,
                    rag_release_id.value,
                ),
            )
        return self.get(rag_release_id)


class PostgresRagReleaseMembershipRepository:
    """Reads and writes ``rag_release_memberships``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def add(self, membership: RagReleaseMembership) -> RagReleaseMembership:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rag_release_memberships ("
                " rag_release_id, project_id, ordinal, source_document_revision_id,"
                " normalized_document_id, chunk_bundle_id, embedding_bundle_id,"
                " materialization_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    membership.rag_release_id.value,
                    membership.project_id.value,
                    membership.ordinal,
                    membership.source_document_revision_id.value,
                    membership.normalized_document_id,
                    membership.chunk_bundle_id,
                    membership.embedding_bundle_id,
                    membership.materialization_id,
                ),
            )
        return membership

    def list_for_release(
        self, rag_release_id: PlatformId
    ) -> list[RagReleaseMembership]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT rag_release_id, project_id, ordinal,"
                " source_document_revision_id, normalized_document_id,"
                " chunk_bundle_id, embedding_bundle_id, materialization_id"
                " FROM rag_release_memberships"
                " WHERE rag_release_id = %s ORDER BY ordinal",
                (rag_release_id.value,),
            )
            rows = cursor.fetchall()
        return [_row_to_membership(row) for row in rows]


def _row_to_release(row) -> RagRelease:
    return RagRelease(
        rag_release_id=_pid(IdentityKind.RAG_RELEASE, str(row[0])),
        project_id=_pid(IdentityKind.PROJECT, str(row[1])),
        rag_variant_id=_pid(IdentityKind.RAG_VARIANT, str(row[2])),
        corpus_snapshot_id=_pid(IdentityKind.CORPUS_SNAPSHOT, str(row[3])),
        target_binding_key=str(row[4]),
        release_number=int(row[5]),
        state=ReleaseState(str(row[6])),
        release_manifest_hash=row[7],
        created_by=str(row[8]),
        created_at=row[9],
        validated_at=row[10],
        reason=row[11],
    )


def _row_to_membership(row) -> RagReleaseMembership:
    return RagReleaseMembership(
        rag_release_id=_pid(IdentityKind.RAG_RELEASE, str(row[0])),
        project_id=_pid(IdentityKind.PROJECT, str(row[1])),
        ordinal=int(row[2]),
        source_document_revision_id=_pid(
            IdentityKind.SOURCE_DOCUMENT_REVISION, str(row[3])
        ),
        normalized_document_id=str(row[4]),
        chunk_bundle_id=str(row[5]),
        embedding_bundle_id=str(row[6]),
        materialization_id=str(row[7]),
    )
