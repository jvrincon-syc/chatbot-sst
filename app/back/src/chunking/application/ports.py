from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from chunking.domain.models import ChunkBundle, ChunkingProfile, NormalizedDocumentBundle


class TokenCounterPort(Protocol):
    """Counts canonical tokens without exposing a tokenizer implementation."""

    def count_tokens(self, text: str) -> int:
        """Return the canonical token count for non-empty chunk text."""


class StructuralChunkerPort(Protocol):
    """Builds validated structural chunks from a normalized document."""

    def chunk(
        self,
        document: NormalizedDocumentBundle,
        profile: ChunkingProfile,
    ) -> ChunkBundle:
        """Return the deterministic chunk bundle for one document and profile."""


@dataclass(frozen=True)
class StoredChunkBundleMetadata:
    """Persisted bundle identity used for idempotent chunking runs."""

    document_id: str
    normalized_relpath: str
    profile_id: str
    profile_fingerprint: str
    bundle_fingerprint: str


class ChunkBundleRepositoryPort(Protocol):
    """Persists complete chunk outputs through an infrastructure adapter."""

    def replace(
        self,
        *,
        document: NormalizedDocumentBundle,
        bundle: ChunkBundle,
    ) -> StoredChunkBundleMetadata:
        """Atomically replace chunks for the bundle document and profile."""

    def read_metadata(
        self,
        *,
        document: NormalizedDocumentBundle,
    ) -> StoredChunkBundleMetadata | None:
        """Return persisted bundle identity when the document was already chunked."""
