from __future__ import annotations

from dataclasses import dataclass

from chunking.application.ports import StoredChunkBundleMetadata
from chunking.domain.models import ChunkBundle, NormalizedDocumentBundle
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from embedding.domain.models import ChunkBundleRef
from embedding.infrastructure.postgres.repositories import PostgresChunkBundleRepository


@dataclass(frozen=True)
class FilesystemBackedPostgresChunkBundleRepository(FilesystemChunkBundleRepository):
    """Persist chunk artifacts on disk and register their ledger rows in PostgreSQL.

    ``project_id`` es el dueño de plataforma (ADR-008): se estampa en la fila
    ``chunk_bundles`` para que el bundle nazca con proyecto desde raw→chunk. La BD lo
    exige NOT NULL, así que registrar sin ``project_id`` falla cerrado en el INSERT.
    """

    ledger: PostgresChunkBundleRepository
    connection: object
    project_id: str | None = None
    close_connection_on_close: bool = False

    def replace(
        self,
        *,
        document: NormalizedDocumentBundle,
        bundle: ChunkBundle,
    ) -> StoredChunkBundleMetadata:
        metadata = super().replace(document=document, bundle=bundle)
        self._register(metadata)
        return metadata

    def read_metadata(
        self,
        *,
        document: NormalizedDocumentBundle,
    ) -> StoredChunkBundleMetadata | None:
        metadata = super().read_metadata(document=document)
        if metadata is not None:
            self._register(metadata)
        return metadata

    def close(self) -> None:
        if not self.close_connection_on_close:
            return
        close = getattr(self.connection, "close", None)
        if callable(close):
            close()

    def _register(self, metadata: StoredChunkBundleMetadata) -> None:
        try:
            self.ledger.ensure_registered(
                ChunkBundleRef(
                    chunk_bundle_id=metadata.bundle_fingerprint,
                    bundle_fingerprint=metadata.bundle_fingerprint,
                    project_id=self.project_id,
                    profile_id=metadata.profile_id,
                    profile_fingerprint=metadata.profile_fingerprint,
                    corpus_version=metadata.corpus_version,
                    source_document_id=metadata.document_id,
                    artifact_relpath=metadata.artifact_relpath,
                    source_relpath=metadata.source_relpath,
                    normalized_relpath=metadata.normalized_relpath,
                    source_hash=metadata.source_hash,
                    parent_count=metadata.parent_count,
                    child_count=metadata.child_count,
                    status="verified",
                )
            )
            commit = getattr(self.connection, "commit", None)
            if callable(commit):
                commit()
        except Exception:
            rollback = getattr(self.connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
