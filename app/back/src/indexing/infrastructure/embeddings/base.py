from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from indexing.application.embedding_provider import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingDimensionError,
    EmbeddingInputError,
    EmbeddingProviderResponseError,
)
from indexing.domain.models import IndexingProfile
from indexing.domain.profiles import DistanceMetric


def validate_texts(texts: Sequence[str]) -> list[str]:
    """Validate and normalize an embedding input batch."""

    if not texts:
        raise EmbeddingInputError("embedding input batch cannot be empty")
    normalized = [text.strip() for text in texts]
    if any(not text for text in normalized):
        raise EmbeddingInputError("embedding input texts cannot be blank")
    return normalized


def embedding_batch(
    *,
    vectors: Any,
    expected_count: int,
    profile: IndexingProfile,
    distance_metric: DistanceMetric,
    normalized: bool,
    capabilities: EmbeddingCapabilities,
) -> EmbeddingBatch:
    """Build a validated dense embedding batch."""

    dense_vectors = _coerce_vectors(vectors)
    if len(dense_vectors) != expected_count:
        raise EmbeddingProviderResponseError(
            "embedding response count does not match input batch"
        )
    for vector in dense_vectors:
        if len(vector) != profile.embedding_dimension:
            raise EmbeddingDimensionError(
                "embedding dimension does not match selected profile"
            )
    return EmbeddingBatch(
        vectors=dense_vectors,
        provider=profile.embedding_provider,
        model=profile.embedding_model,
        dimension=profile.embedding_dimension,
        distance_metric=distance_metric,
        normalized=normalized,
        capabilities=capabilities,
        profile_id=profile.profile_id,
    )


def _coerce_vectors(vectors: Any) -> list[list[float]]:
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    if not isinstance(vectors, Iterable):
        raise EmbeddingProviderResponseError("embedding response is not iterable")
    dense_vectors: list[list[float]] = []
    for vector in vectors:
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        if not isinstance(vector, Iterable) or isinstance(vector, (str, bytes)):
            raise EmbeddingProviderResponseError("embedding vector is not iterable")
        dense_vectors.append([float(value) for value in vector])
    return dense_vectors
