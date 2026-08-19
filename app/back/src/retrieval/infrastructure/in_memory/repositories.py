"""In-memory retrieval adapters backed by the in-memory vector store.

They mirror the PostgreSQL behaviour, including the unique active profile per
``(consumer_scope_type, consumer_scope_id, corpus_version)`` enforced by
``idx_retrieval_profiles_one_active_scope_corpus``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import math

from indexing.domain.bundle_first import IndexingNodeRecord
from indexing.infrastructure.in_memory.bundle_first import (
    InMemoryBundleVectorRepository,
    InMemoryIndexingNodeWriter,
)
from retrieval.domain.errors import RetrievalProfileNotFound
from retrieval.domain.models import RetrievalProfile, RetrievedEvidence


class InMemoryRetrievalProfileRepository:
    """Deterministic ``retrieval_profiles`` double."""

    def __init__(self) -> None:
        self._profiles: dict[str, RetrievalProfile] = {}

    def upsert(self, profile: RetrievalProfile) -> RetrievalProfile:
        """Insert or update one retrieval profile."""

        self._profiles[profile.retrieval_profile_id] = profile
        return profile

    def get(self, retrieval_profile_id: str) -> RetrievalProfile:
        """Return one profile or raise ``RetrievalProfileNotFound``."""

        profile = self._profiles.get(retrieval_profile_id)
        if profile is None:
            raise RetrievalProfileNotFound(
                f"retrieval profile not found: {retrieval_profile_id}"
            )
        return profile

    def list_profiles(self) -> list[RetrievalProfile]:
        """Return every retrieval profile."""

        return list(self._profiles.values())

    def find_active(
        self,
        *,
        project_id: str,
        consumer_scope_type: str,
        consumer_scope_id: str,
        corpus_version: str | None = None,
    ) -> RetrievalProfile | None:
        """Return the single active profile of one consumer scope."""

        for profile in self._profiles.values():
            if (
                profile.active
                and profile.project_id == project_id
                and profile.consumer_scope_type == consumer_scope_type
                and profile.consumer_scope_id == consumer_scope_id
                and (corpus_version is None or profile.corpus_version == corpus_version)
            ):
                return profile
        return None

    def activate(
        self,
        *,
        retrieval_profile_id: str,
        validated_at: datetime,
    ) -> RetrievalProfile:
        """Activate one profile and deactivate the previous one in the scope."""

        profile = self.get(retrieval_profile_id)
        for other_id, other in list(self._profiles.items()):
            if (
                other_id != retrieval_profile_id
                and other.active
                and other.project_id == profile.project_id
                and other.consumer_scope_type == profile.consumer_scope_type
                and other.consumer_scope_id == profile.consumer_scope_id
                and other.corpus_version == profile.corpus_version
            ):
                self._profiles[other_id] = other.model_copy(update={"active": False})
        activated = profile.model_copy(
            update={
                "active": True,
                "validation_status": "passed",
                "validated_at": validated_at,
            }
        )
        self._profiles[retrieval_profile_id] = activated
        return activated

    def record_runtime_status(
        self,
        *,
        retrieval_profile_id: str,
        last_runtime_status: str,
    ) -> RetrievalProfile:
        """Persist the outcome of the latest retrieval attempt."""

        profile = self.get(retrieval_profile_id)
        updated = profile.model_copy(update={"last_runtime_status": last_runtime_status})
        self._profiles[retrieval_profile_id] = updated
        return updated


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass
class InMemoryVectorSearch:
    """Vector search restricted to the active rows of one lane."""

    vectors: InMemoryBundleVectorRepository
    nodes: InMemoryIndexingNodeWriter

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

        scored: list[RetrievedEvidence] = []
        for (table, _bundle_id, node_id), stored in self.vectors.rows.items():
            if table != vector_table or not stored.is_active:
                continue
            if (
                stored.record.project_id != project_id
                or stored.embedding_profile_id != embedding_profile_id
                or stored.indexing_target_id != indexing_target_id
                or stored.record.corpus_version != corpus_version
            ):
                continue
            node = self.nodes.nodes.get(node_id)
            if node is None:
                continue
            scored.append(
                _evidence_from_node(
                    node=node,
                    score=_cosine(query_embedding, stored.record.embedding),
                    source="vector",
                    embedding_profile_id=embedding_profile_id,
                    embedding_bundle_id=stored.record.embedding_bundle_id,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

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

        return len(
            self._active(
                vector_table=vector_table,
                project_id=project_id,
                embedding_profile_id=embedding_profile_id,
                indexing_target_id=indexing_target_id,
                corpus_version=corpus_version,
            )
        )

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

        return len(
            {
                stored.record.document_id
                for stored in self._active(
                    vector_table=vector_table,
                    project_id=project_id,
                    embedding_profile_id=embedding_profile_id,
                    indexing_target_id=indexing_target_id,
                    corpus_version=corpus_version,
                )
            }
        )

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

        return sorted(
            {
                stored.record.embedding_bundle_id
                for stored in self._active(
                    vector_table=vector_table,
                    project_id=project_id,
                    embedding_profile_id=embedding_profile_id,
                    indexing_target_id=indexing_target_id,
                    corpus_version=corpus_version,
                )
            }
        )

    def _active(
        self,
        *,
        vector_table: str,
        project_id: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        corpus_version: str,
    ) -> list[object]:
        return [
            stored
            for (table, _bundle_id, _node_id), stored in self.vectors.rows.items()
            if table == vector_table
            and stored.is_active
            and stored.record.project_id == project_id
            and stored.embedding_profile_id == embedding_profile_id
            and stored.indexing_target_id == indexing_target_id
            and stored.record.corpus_version == corpus_version
        ]


@dataclass
class InMemoryLexicalSearch:
    """Naive lexical search over the durable node records."""

    nodes: InMemoryIndexingNodeWriter

    def search(
        self,
        *,
        project_id: str,
        query: str,
        embedding_profile_id: str,
        corpus_version: str,
        top_k: int,
    ) -> list[RetrievedEvidence]:
        """Return the closest child nodes by naive token overlap.

        ponytail: token overlap, not tsvector ranking. The PostgreSQL adapter is
        the real ranker; this double only needs deterministic ordering.
        """

        terms = {token for token in query.lower().split() if token}
        scored: list[RetrievedEvidence] = []
        for node in self.nodes.nodes.values():
            if (
                node.node_role != "child"
                or node.project_id != project_id
                or node.corpus_version != corpus_version
            ):
                continue
            tokens = {token for token in node.text.lower().split() if token}
            overlap = len(terms & tokens)
            if overlap == 0:
                continue
            scored.append(
                _evidence_from_node(
                    node=node,
                    score=float(overlap),
                    source="lexical",
                    embedding_profile_id=embedding_profile_id,
                    embedding_bundle_id=None,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


@dataclass
class InMemoryParentExpansion:
    """Expand child evidence into its parent node."""

    nodes: InMemoryIndexingNodeWriter

    def expand(
        self,
        *,
        project_id: str,
        parent_node_ids: Sequence[str],
        embedding_profile_id: str,
        corpus_version: str,
    ) -> dict[str, RetrievedEvidence]:
        """Return parent evidence keyed by ``parent_node_id``."""

        parents: dict[str, RetrievedEvidence] = {}
        for parent_node_id in parent_node_ids:
            node = self.nodes.nodes.get(parent_node_id)
            if (
                node is None
                or node.project_id != project_id
                or node.corpus_version != corpus_version
            ):
                continue
            parents[parent_node_id] = _evidence_from_node(
                node=node,
                score=0.0,
                source="lexical",
                embedding_profile_id=embedding_profile_id,
                embedding_bundle_id=None,
            )
        return parents


def _evidence_from_node(
    *,
    node: IndexingNodeRecord,
    score: float,
    source: str,
    embedding_profile_id: str,
    embedding_bundle_id: str | None,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        node_id=node.node_id,
        document_id=node.document_id,
        parent_node_id=node.parent_node_id,
        child_chunk_id=node.node_id,
        text=node.text,
        score=score,
        source=source,  # type: ignore[arg-type]
        page_start=node.page_start,
        page_end=node.page_end,
        section_title=node.section_title,
        section_path=node.section_path,
        metadata=dict(node.metadata),
        embedding_profile_id=embedding_profile_id,
        corpus_version=str(node.corpus_version or ""),
        embedding_bundle_id=embedding_bundle_id,
    )
