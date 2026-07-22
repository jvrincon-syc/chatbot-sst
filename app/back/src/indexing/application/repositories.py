from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from llama_index.core.schema import BaseNode

from indexing.domain.models import IndexableDocument
from indexing.domain.profiles import IngestionOrigin
from indexing.domain.profiles import ResolvedIndexingProfile


class ProfileRegistry(Protocol):
    def get(self, profile_id: str) -> ResolvedIndexingProfile:
        """Return an immutable indexing profile by id."""


class ProfileResolver(Protocol):
    def resolve(
        self,
        *,
        profile_id: str,
        ingestion_origin: IngestionOrigin,
    ) -> ResolvedIndexingProfile:
        """Resolve and validate an indexing profile for a normalized lane."""


class NormalizedDocumentRepository(Protocol):
    def replace_document(
        self,
        *,
        document: IndexableDocument,
        ingestion_origin: IngestionOrigin,
        artifact_fingerprint: str,
        corpus_version: str,
    ) -> None:
        """Persist normalized document provenance before indexing nodes."""


class NodeRepository(Protocol):
    def replace_document_nodes(
        self,
        *,
        document_id: str,
        nodes: Sequence[BaseNode],
    ) -> int:
        """Replace durable nodes for one normalized document."""


class VectorRepository(Protocol):
    def replace_document_vectors(
        self,
        *,
        document_id: str,
        profile: ResolvedIndexingProfile,
        nodes: Sequence[BaseNode],
        embeddings: Sequence[list[float]],
    ) -> int:
        """Replace vectors for one document in one profile table."""
