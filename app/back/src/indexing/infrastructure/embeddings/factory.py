from __future__ import annotations

import hashlib
from dataclasses import dataclass

from indexing.application.embedding_provider import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProvider,
)
from indexing.domain.models import IndexingProfile
from indexing.domain.profiles import DistanceMetric
from indexing.infrastructure.embeddings.bge import BgeEmbeddingProvider
from indexing.infrastructure.embeddings.cohere import CohereEmbeddingProvider
from indexing.infrastructure.embeddings.base import embedding_batch, validate_texts
from indexing.infrastructure.embeddings.settings import EmbeddingSettings
from indexing.infrastructure.embeddings.voyage import VoyageEmbeddingProvider


class EmbeddingProfileMismatchError(ValueError):
    """Embedding profile is incompatible with the target store."""


class UnknownEmbeddingProviderError(ValueError):
    """Embedding provider name is not registered."""


@dataclass
class DeterministicEmbeddingProvider:
    profile: IndexingProfile
    settings: EmbeddingSettings

    @property
    def provider_name(self) -> str:
        return self.profile.embedding_provider

    @property
    def model_name(self) -> str:
        return self.profile.embedding_model

    @property
    def dimension(self) -> int:
        return self.profile.embedding_dimension

    @property
    def distance_metric(self) -> DistanceMetric:
        return self.settings.distance_metric

    @property
    def normalized(self) -> bool:
        return False

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities()

    @property
    def batch_size(self) -> int:
        return self.settings.batch_size

    @property
    def retries(self) -> int:
        return 0

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        batch_texts = validate_texts(texts)
        vectors = [
            _deterministic_vector(text, self.profile.embedding_dimension)
            for text in batch_texts
        ]
        return embedding_batch(
            vectors=vectors,
            expected_count=len(batch_texts),
            profile=self.profile,
            distance_metric=self.distance_metric,
            normalized=self.normalized,
            capabilities=self.capabilities,
        )

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return self.embed_documents(texts)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts).vectors


class EmbeddingFactory:
    def __init__(
        self,
        *,
        expected_dimension: int | None = None,
        settings: EmbeddingSettings | None = None,
    ) -> None:
        self._expected_dimension = expected_dimension
        self._settings = settings or EmbeddingSettings.from_env()
        self._providers: dict[tuple[str, str, int, str], EmbeddingProvider] = {}

    def create(self, profile: IndexingProfile) -> EmbeddingProvider:
        if (
            self._expected_dimension is not None
            and profile.embedding_dimension != self._expected_dimension
        ):
            raise EmbeddingProfileMismatchError(
                "embedding dimension does not match the target vector store"
            )

        cache_key = (
            profile.profile_id,
            profile.embedding_provider,
            profile.embedding_dimension,
            self._settings.distance_metric,
        )
        if cache_key in self._providers:
            return self._providers[cache_key]

        if profile.embedding_provider == "mock":
            provider: EmbeddingProvider = DeterministicEmbeddingProvider(
                profile=profile,
                settings=self._settings,
            )
        elif profile.embedding_provider == "bge":
            provider = BgeEmbeddingProvider(profile=profile, settings=self._settings)
        elif profile.embedding_provider == "voyage":
            provider = VoyageEmbeddingProvider(profile=profile, settings=self._settings)
        elif profile.embedding_provider == "cohere":
            provider = CohereEmbeddingProvider(profile=profile)
        else:
            raise UnknownEmbeddingProviderError(
                f"unknown embedding provider: {profile.embedding_provider}"
            )
        self._providers[cache_key] = provider
        return provider


def _deterministic_vector(text: str, dimension: int) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend((byte / 255.0) for byte in digest)
        counter += 1
    return values[:dimension]
