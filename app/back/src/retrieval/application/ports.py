"""Application ports for retrieval profiles and durable search."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from retrieval.domain.models import RetrievalProfile, RetrievedEvidence


class RetrievalProfileRepository(Protocol):
    """Durable read/write access to ``retrieval_profiles``."""

    def upsert(self, profile: RetrievalProfile) -> RetrievalProfile:
        """Insert or update one retrieval profile."""

    def get(self, retrieval_profile_id: str) -> RetrievalProfile:
        """Return one profile or raise ``RetrievalProfileNotFound``."""

    def list_profiles(self) -> list[RetrievalProfile]:
        """Return every retrieval profile."""

    def find_active(
        self,
        *,
        project_id: str,
        consumer_scope_type: str,
        consumer_scope_id: str,
        corpus_version: str | None = None,
    ) -> RetrievalProfile | None:
        """Return the single active profile of one consumer scope."""

    def activate(
        self,
        *,
        retrieval_profile_id: str,
        validated_at: datetime,
    ) -> RetrievalProfile:
        """Activate one profile and deactivate the previous one in the scope."""

    def record_runtime_status(
        self,
        *,
        retrieval_profile_id: str,
        last_runtime_status: str,
    ) -> RetrievalProfile:
        """Persist the outcome of the latest retrieval attempt."""


class VectorSearchPort(Protocol):
    """pgvector search restricted to one active lane."""

    def search(
        self,
        *,
        project_id: str,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
        distance_metric: str,
        query_embedding: Sequence[float],
        top_k: int,
    ) -> list[RetrievedEvidence]:
        """Return the closest active child chunks of one lane."""

    def count_active_rows(
        self,
        *,
        project_id: str,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> int:
        """Count the active vector rows currently serving one lane."""

    def count_active_documents(
        self,
        *,
        project_id: str,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> int:
        """Count the distinct documents currently serving one lane."""

    def active_bundle_ids(
        self,
        *,
        project_id: str,
        vector_table: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> list[str]:
        """Return the embedding bundle ids currently active in one lane."""


class LexicalSearchPort(Protocol):
    """Full-text search over ``indexing_nodes``."""

    def search(
        self,
        *,
        project_id: str,
        query: str,
        embedding_profile_id: str,
        corpus_version: str,
        top_k: int,
    ) -> list[RetrievedEvidence]:
        """Return the closest child nodes by full-text rank."""


class ParentExpansionPort(Protocol):
    """Expand retrieved child evidence into its parent node."""

    def expand(
        self,
        *,
        project_id: str,
        parent_node_ids: Sequence[str],
        embedding_profile_id: str,
        corpus_version: str,
    ) -> dict[str, RetrievedEvidence]:
        """Return parent evidence keyed by ``parent_node_id``."""
