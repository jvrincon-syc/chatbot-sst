from __future__ import annotations

import hashlib
from dataclasses import dataclass

from indexing.application.embedding_provider import EmbeddingProvider
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import BgeEmbeddingProvider
from indexing.infrastructure.embeddings.cohere import CohereEmbeddingProvider
from indexing.infrastructure.embeddings.voyage import VoyageEmbeddingProvider


class EmbeddingProfileMismatchError(ValueError):
    """Embedding profile is incompatible with the target store."""


class UnknownEmbeddingProviderError(ValueError):
    """Embedding provider name is not registered."""


@dataclass(frozen=True)
class DeterministicEmbeddingProvider:
    profile: IndexingProfile

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(text, self.profile.embedding_dimension) for text in texts]


class EmbeddingFactory:
    def __init__(self, *, expected_dimension: int | None = None) -> None:
        self._expected_dimension = expected_dimension

    def create(self, profile: IndexingProfile) -> EmbeddingProvider:
        if (
            self._expected_dimension is not None
            and profile.embedding_dimension != self._expected_dimension
        ):
            raise EmbeddingProfileMismatchError(
                "embedding dimension does not match the target vector store"
            )

        if profile.embedding_provider == "mock":
            return DeterministicEmbeddingProvider(profile=profile)
        if profile.embedding_provider == "bge":
            return BgeEmbeddingProvider(profile=profile)
        if profile.embedding_provider == "voyage":
            return VoyageEmbeddingProvider(profile=profile)
        if profile.embedding_provider == "cohere":
            return CohereEmbeddingProvider(profile=profile)
        raise UnknownEmbeddingProviderError(
            f"unknown embedding provider: {profile.embedding_provider}"
        )


def _deterministic_vector(text: str, dimension: int) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend((byte / 255.0) for byte in digest)
        counter += 1
    return values[:dimension]
