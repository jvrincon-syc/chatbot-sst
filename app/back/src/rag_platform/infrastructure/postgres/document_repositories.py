"""PostgreSQL adapters for platform documents, revisions and corpus snapshots.

Every statement is parameterized and every table already exists: this module
reflects the schema frozen by migrations ``20260810_02`` and ``20260810_03`` and
never issues DDL, mirroring the Fase 1 catalog adapters. Document content is
never stored here; only the raw content hash and load traceability.
"""

from __future__ import annotations

from collections.abc import Sequence

from rag_platform.domain.errors import (
    CorpusSnapshotNotFound,
    SourceDocumentRevisionNotFound,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    CorpusSnapshot,
    CorpusSnapshotDocument,
    EligibilityDecision,
    NormalizedDocumentArtifact,
    RevisionReviewState,
    SourceDocument,
    SourceDocumentRevision,
)


def _pid(kind: IdentityKind, value: str) -> PlatformId:
    return PlatformId(kind=kind, value=value)


class PostgresSourceDocumentRepository:
    """Reads and writes ``project_documents`` and ``source_document_revisions``."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_document(self, logical_document_id: PlatformId) -> SourceDocument | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT logical_document_id, project_id, source_relpath, created_at"
                " FROM project_documents WHERE logical_document_id = %s",
                (logical_document_id.value,),
            )
            row = cursor.fetchone()
        return None if row is None else self._row_to_document(row)

    def upsert_document(self, document: SourceDocument) -> SourceDocument:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO project_documents"
                " (logical_document_id, project_id, source_relpath, created_at)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (logical_document_id) DO NOTHING",
                (
                    document.logical_document_id.value,
                    document.project_id.value,
                    document.source_relpath,
                    document.created_at,
                ),
            )
        return document

    def find_revision_by_hash(
        self, logical_document_id: PlatformId, raw_content_hash: str
    ) -> SourceDocumentRevision | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_REVISION_COLUMNS} FROM source_document_revisions"
                " WHERE logical_document_id = %s AND raw_content_hash = %s",
                (logical_document_id.value, raw_content_hash),
            )
            row = cursor.fetchone()
        return None if row is None else self._row_to_revision(row)

    def get_revision(
        self, source_document_revision_id: PlatformId
    ) -> SourceDocumentRevision:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_REVISION_COLUMNS} FROM source_document_revisions"
                " WHERE source_document_revision_id = %s",
                (source_document_revision_id.value,),
            )
            row = cursor.fetchone()
        if row is None:
            raise SourceDocumentRevisionNotFound(source_document_revision_id.value)
        return self._row_to_revision(row)

    def add_revision(
        self, revision: SourceDocumentRevision
    ) -> SourceDocumentRevision:
        with self._connection.cursor() as cursor:
            # Immutable: a re-uploaded identical revision is a no-op insert.
            cursor.execute(
                "INSERT INTO source_document_revisions"
                " (source_document_revision_id, logical_document_id, project_id,"
                " source_relpath, raw_content_hash, file_size, uploaded_by,"
                " uploaded_at, review_state)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (source_document_revision_id) DO NOTHING",
                (
                    revision.source_document_revision_id.value,
                    revision.logical_document_id.value,
                    revision.project_id.value,
                    revision.source_relpath,
                    revision.raw_content_hash,
                    revision.file_size,
                    revision.uploaded_by,
                    revision.uploaded_at,
                    revision.review_state.value,
                ),
            )
        return revision

    @staticmethod
    def _row_to_document(row: Sequence[object]) -> SourceDocument:
        return SourceDocument(
            logical_document_id=_pid(IdentityKind.SOURCE_DOCUMENT, str(row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            source_relpath=str(row[2]),
            created_at=row[3],  # type: ignore[arg-type]
        )

    @staticmethod
    def _row_to_revision(row: Sequence[object]) -> SourceDocumentRevision:
        return SourceDocumentRevision(
            source_document_revision_id=_pid(
                IdentityKind.SOURCE_DOCUMENT_REVISION, str(row[0])
            ),
            logical_document_id=_pid(IdentityKind.SOURCE_DOCUMENT, str(row[1])),
            project_id=_pid(IdentityKind.PROJECT, str(row[2])),
            source_relpath=str(row[3]),
            raw_content_hash=str(row[4]),
            file_size=int(row[5]),  # type: ignore[arg-type]
            uploaded_by=str(row[6]),
            uploaded_at=row[7],  # type: ignore[arg-type]
            review_state=RevisionReviewState(str(row[8])),
        )


_REVISION_COLUMNS = (
    "source_document_revision_id, logical_document_id, project_id, source_relpath,"
    " raw_content_hash, file_size, uploaded_by, uploaded_at, review_state"
)


class PostgresNormalizedArtifactRepository:
    """Reads and writes ``project_normalized_documents`` by exact identity."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find(
        self,
        *,
        project_id: PlatformId,
        source_document_revision_id: PlatformId,
        processing_profile_fingerprint: str,
    ) -> NormalizedDocumentArtifact | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT project_id, source_document_revision_id,"
                " processing_profile_fingerprint, schema_version, artifact_relpath"
                " FROM project_normalized_documents"
                " WHERE project_id = %s AND source_document_revision_id = %s"
                " AND processing_profile_fingerprint = %s",
                (
                    project_id.value,
                    source_document_revision_id.value,
                    processing_profile_fingerprint,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return NormalizedDocumentArtifact(
            project_id=_pid(IdentityKind.PROJECT, str(row[0])),
            source_document_revision_id=_pid(
                IdentityKind.SOURCE_DOCUMENT_REVISION, str(row[1])
            ),
            processing_profile_fingerprint=str(row[2]),
            schema_version=str(row[3]),
            artifact_relpath=None if row[4] is None else str(row[4]),
        )

    def add(
        self, artifact: NormalizedDocumentArtifact
    ) -> NormalizedDocumentArtifact:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO project_normalized_documents"
                " (project_id, source_document_revision_id,"
                " processing_profile_fingerprint, schema_version, artifact_relpath)"
                " VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (project_id, source_document_revision_id,"
                " processing_profile_fingerprint) DO UPDATE SET"
                " schema_version = EXCLUDED.schema_version,"
                " artifact_relpath = COALESCE("
                " EXCLUDED.artifact_relpath,"
                " project_normalized_documents.artifact_relpath"
                " )",
                (
                    artifact.project_id.value,
                    artifact.source_document_revision_id.value,
                    artifact.processing_profile_fingerprint,
                    artifact.schema_version,
                    artifact.artifact_relpath,
                ),
            )
        return artifact


class PostgresCorpusSnapshotRepository:
    """Reads and writes ``corpus_snapshots`` and their ordered memberships."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def find_by_manifest(
        self, project_id: PlatformId, manifest_hash: str
    ) -> CorpusSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT corpus_snapshot_id, project_id, manifest_hash,"
                " document_count, created_at FROM corpus_snapshots"
                " WHERE project_id = %s AND manifest_hash = %s",
                (project_id.value, manifest_hash),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "SELECT ordinal, source_document_revision_id, eligibility_decision"
                " FROM corpus_snapshot_documents WHERE corpus_snapshot_id = %s"
                " ORDER BY ordinal",
                (str(row[0]),),
            )
            member_rows = cursor.fetchall()
        return self._row_to_snapshot(row, member_rows)

    def get(self, corpus_snapshot_id: PlatformId) -> CorpusSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT corpus_snapshot_id, project_id, manifest_hash,"
                " document_count, created_at FROM corpus_snapshots"
                " WHERE corpus_snapshot_id = %s",
                (corpus_snapshot_id.value,),
            )
            row = cursor.fetchone()
            if row is None:
                raise CorpusSnapshotNotFound(corpus_snapshot_id.value)
            cursor.execute(
                "SELECT ordinal, source_document_revision_id, eligibility_decision"
                " FROM corpus_snapshot_documents WHERE corpus_snapshot_id = %s"
                " ORDER BY ordinal",
                (corpus_snapshot_id.value,),
            )
            member_rows = cursor.fetchall()
        return self._row_to_snapshot(row, member_rows)

    def add(self, snapshot: CorpusSnapshot) -> CorpusSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO corpus_snapshots"
                " (corpus_snapshot_id, project_id, manifest_hash, document_count,"
                " created_at) VALUES (%s, %s, %s, %s, %s)",
                (
                    snapshot.corpus_snapshot_id.value,
                    snapshot.project_id.value,
                    snapshot.manifest_hash,
                    snapshot.document_count,
                    snapshot.created_at,
                ),
            )
            for member in snapshot.documents:
                cursor.execute(
                    "INSERT INTO corpus_snapshot_documents"
                    " (corpus_snapshot_id, ordinal, source_document_revision_id,"
                    " eligibility_decision) VALUES (%s, %s, %s, %s)",
                    (
                        snapshot.corpus_snapshot_id.value,
                        member.ordinal,
                        member.source_document_revision_id.value,
                        member.eligibility_decision.value,
                    ),
                )
        return snapshot

    @staticmethod
    def _row_to_snapshot(
        row: Sequence[object], member_rows: Sequence[Sequence[object]]
    ) -> CorpusSnapshot:
        documents = tuple(
            CorpusSnapshotDocument(
                ordinal=int(m[0]),  # type: ignore[arg-type]
                source_document_revision_id=_pid(
                    IdentityKind.SOURCE_DOCUMENT_REVISION, str(m[1])
                ),
                eligibility_decision=EligibilityDecision(str(m[2])),
            )
            for m in member_rows
        )
        return CorpusSnapshot(
            corpus_snapshot_id=_pid(IdentityKind.CORPUS_SNAPSHOT, str(row[0])),
            project_id=_pid(IdentityKind.PROJECT, str(row[1])),
            documents=documents,
            document_count=int(row[3]),  # type: ignore[arg-type]
            manifest_hash=str(row[2]),
            created_at=row[4],  # type: ignore[arg-type]
        )
