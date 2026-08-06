"""The single productive caller of ``embed_queries()``.

Query vectors must land in exactly the same space as the indexed document
vectors, so this service refuses to embed anything until the durable retrieval
profile, the durable embedding profile and the live engine agree on provider,
model, revision, dimension, normalization, metric and fingerprint.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import logging

from core.logging.observability import EventStatus, ObservabilityDomain
from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    EmbeddingEngineRegistry,
    EmbeddingProfileRepository,
)
from embedding.domain.errors import (
    EmbeddingDomainError,
    EmbeddingEngineNotFound,
    EmbeddingEngineSemanticMismatch,
    EmbeddingEngineUnavailable,
    QueryEmbeddingUnsupported,
)
from embedding.domain.models import EmbeddingProfile
from retrieval.domain.errors import RetrievalProfileBlocked
from retrieval.domain.models import RetrievalProfile


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueryEmbedding:
    """One query vector plus the lane it is allowed to be searched in."""

    vector: list[float]
    embedding_profile_id: str
    indexing_target_id: str
    corpus_version: str
    dimension: int
    distance_metric: str
    model_revision: str


class QueryEmbeddingService:
    """Embed queries for exactly one active retrieval profile."""

    def __init__(
        self,
        *,
        profiles: EmbeddingProfileRepository,
        registry: EmbeddingEngineRegistry,
    ) -> None:
        self._profiles = profiles
        self._registry = registry

    def resolve_profile(self, retrieval_profile: RetrievalProfile) -> EmbeddingProfile:
        """Return the durable embedding profile a retrieval profile points at.

        Raises:
            RetrievalProfileBlocked: When the retrieval profile is not usable or
                the embedding profile is not enabled for queries.
        """

        if not retrieval_profile.is_usable:
            raise RetrievalProfileBlocked(
                f"retrieval profile {retrieval_profile.retrieval_profile_id} is not active"
            )
        profile = self._profiles.get(retrieval_profile.embedding_profile_id)
        if not profile.can_embed_queries:
            raise RetrievalProfileBlocked(
                f"embedding profile {profile.profile_id} is not enabled for queries"
            )
        return profile

    def embed_queries(
        self,
        *,
        retrieval_profile: RetrievalProfile,
        queries: Sequence[str],
    ) -> list[QueryEmbedding]:
        """Embed queries with the exact engine of the indexed lane.

        Raises:
            RetrievalProfileBlocked: When the profile is not usable.
            EmbeddingEngineUnavailable: When the runtime cannot be reached.
            QueryEmbeddingUnsupported: When the engine cannot embed queries.
            EmbeddingEngineSemanticMismatch: When the engine drifted.
        """

        if not queries:
            raise ValueError("query batch must not be empty")
        profile = self.resolve_profile(retrieval_profile)
        try:
            engine = self._registry.resolve_query_engine(profile)
        except (EmbeddingEngineNotFound, EmbeddingEngineUnavailable, QueryEmbeddingUnsupported):
            self._emit_blocked(retrieval_profile=retrieval_profile, profile=profile)
            raise

        report = self._registry.validate_engine_compatibility(profile, engine)
        if not report.compatible:
            self._emit_blocked(retrieval_profile=retrieval_profile, profile=profile)
            raise EmbeddingEngineSemanticMismatch(
                "query engine semantics differ from the indexed profile: "
                + ",".join(mismatch.field_name for mismatch in report.mismatches)
            )
        observed_revision = engine.observe_revision()

        try:
            vectors = engine.embed_queries(list(queries))
        except EmbeddingDomainError:
            self._emit_blocked(retrieval_profile=retrieval_profile, profile=profile)
            raise
        if len(vectors) != len(queries):
            raise EmbeddingEngineSemanticMismatch(
                "query engine returned a different number of vectors"
            )
        for vector in vectors:
            if len(vector) != profile.dimension:
                raise EmbeddingEngineSemanticMismatch(
                    "query vector dimension does not match the indexed profile"
                )
        return [
            QueryEmbedding(
                vector=list(vector),
                embedding_profile_id=profile.profile_id,
                indexing_target_id=retrieval_profile.indexing_target_id,
                corpus_version=retrieval_profile.corpus_version,
                dimension=profile.dimension,
                distance_metric=profile.distance_metric,
                model_revision=observed_revision,
            )
            for vector in vectors
        ]

    def _emit_blocked(
        self,
        *,
        retrieval_profile: RetrievalProfile,
        profile: EmbeddingProfile,
    ) -> None:
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.RETRIEVAL,
            event="query_engine_blocked",
            status=EventStatus.BLOCKED,
            message="Query embedding engine is blocked",
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="embed_query",
            attributes={
                "retrieval_profile_id": retrieval_profile.retrieval_profile_id,
                "embedding_profile_id": profile.profile_id,
                "indexing_target_id": retrieval_profile.indexing_target_id,
                "model": profile.model,
                "model_revision": profile.model_revision,
            },
        )
