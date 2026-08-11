"""Ports and adapters used by bundle-first indexing.

None of these ports can embed text. Indexing receives vectors that Embedding
already produced and only decides where and when they become visible.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from embedding.domain.models import EmbeddingProfile
from indexing.domain.bundle_first import (
    IndexingNodeRecord,
    IndexingRun,
    IndexingRunDocument,
    IndexingTarget,
)
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.postgres.vector_repository import AppendOnlyVectorRecord


def resolved_profile_from_embedding_profile(
    profile: EmbeddingProfile,
) -> ResolvedIndexingProfile:
    """Adapt the durable embedding profile to the vector repository contract.

    ``PostgresVectorRepository`` already speaks ``ResolvedIndexingProfile``; this
    adapter keeps the bundle-first path on that single vector API instead of
    growing a second one.
    """

    return ResolvedIndexingProfile(
        profile_id=profile.profile_id,
        ingestion_origin=profile.ingestion_origin,
        chunking_version=profile.chunking_version,
        embedding_provider=profile.provider,
        embedding_model=profile.model,
        embedding_dimension=profile.dimension,
        distance_metric=profile.distance_metric,
        vector_table=profile.vector_table,
        metadata_schema_version=profile.metadata_schema_version,
        active=profile.active,
        config_hash=profile.config_hash,
    )


class TransactionManager(Protocol):
    """Scope one durable document commit."""

    def transaction(self) -> AbstractContextManager[None]:
        """Return a context manager that commits on exit and rolls back on error."""


class IndexingTargetRepository(Protocol):
    """Read ``indexing_targets``: the authority over physical vector tables."""

    def get(self, indexing_target_id: str) -> IndexingTarget:
        """Return one target or raise ``LookupError``."""

    def list_targets(self) -> list[IndexingTarget]:
        """Return every registered target."""


class IndexingNodeWriter(Protocol):
    """Persist neutral node records into ``indexing_nodes``."""

    def replace_document_nodes(
        self,
        *,
        document_id: str,
        nodes: Sequence[IndexingNodeRecord],
    ) -> int:
        """Replace the durable nodes of one document; returns deleted rows."""


class BundleVectorWriter(Protocol):
    """The vector API already published by ``PostgresVectorRepository``."""

    def append_bundle_vectors(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        records: Sequence[AppendOnlyVectorRecord],
    ) -> int:
        """Insert inactive vector rows for one embedding bundle."""

    def activate_bundle(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> None:
        """Activate one bundle and supersede prior active rows of the same documents."""

    def rollback_to_bundle(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        current_embedding_bundle_id: str,
        previous_embedding_bundle_id: str,
    ) -> None:
        """Deactivate the current bundle and reactivate a validated previous one."""

    def count_active_rows(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> int:
        """Count active rows for one bundle in one lane."""


class IndexingRunRepository(Protocol):
    """Durable ``indexing_runs`` ledger."""

    def create(self, run: IndexingRun) -> IndexingRun:
        """Insert a run."""

    def get(self, run_id: str) -> IndexingRun:
        """Return one run or raise ``IndexingRunNotFound``."""

    def find_by_idempotency_key(self, idempotency_key: str) -> IndexingRun | None:
        """Return the run stored under one idempotency key."""

    def list_runs(self) -> list[IndexingRun]:
        """Return every run, newest first."""

    def claim(self, run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once."""

    def update(self, run: IndexingRun) -> IndexingRun:
        """Persist a durable state transition."""

    def list_running(self) -> list[IndexingRun]:
        """Return runs currently marked ``running``."""


class IndexingRunDocumentRepository(Protocol):
    """Durable ``indexing_run_documents`` ledger."""

    def upsert(self, document: IndexingRunDocument) -> IndexingRunDocument:
        """Insert or update one per-document row."""

    def list_for_run(self, run_id: str) -> list[IndexingRunDocument]:
        """Return every document row of one run."""
