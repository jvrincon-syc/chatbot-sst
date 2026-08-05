from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from indexing.domain.models import IndexingProfile
from indexing.domain.profiles import DistanceMetric


class EmbeddingError(RuntimeError):
    """Base error for embedding provider failures."""


class EmbeddingInputError(EmbeddingError):
    """Input texts do not satisfy the embedding contract."""


class EmbeddingDimensionError(EmbeddingError):
    """A provider returned vectors with an unexpected dimension."""


class EmbeddingProviderConfigurationError(EmbeddingError):
    """The selected embedding provider is not configured correctly."""


class EmbeddingProviderAuthenticationError(EmbeddingProviderConfigurationError):
    """A provider requires a missing or invalid credential."""


class EmbeddingProviderTimeoutError(EmbeddingError):
    """The embedding provider timed out."""


class EmbeddingProviderRateLimitError(EmbeddingError):
    """The embedding provider rejected the request due to rate limiting."""


class EmbeddingProviderResponseError(EmbeddingError):
    """The embedding provider returned an invalid response."""


EmbeddingProviderName = Literal["mock", "bge", "voyage", "cohere"]


@dataclass(frozen=True)
class EmbeddingCapabilities:
    """Optional capabilities exposed by an embedding provider."""

    supports_sparse: bool = False
    supports_multimodal: bool = False
    supports_dense: bool = True


@dataclass(frozen=True)
class EmbeddingBatch:
    """Dense embedding batch with profile metadata for validation and persistence."""

    vectors: list[list[float]]
    provider: str
    model: str
    dimension: int
    distance_metric: DistanceMetric
    normalized: bool
    capabilities: EmbeddingCapabilities
    profile_id: str


class EmbeddingProvider(Protocol):
    profile: IndexingProfile

    @property
    def provider_name(self) -> str:
        """Return the stable provider name used in indexing profiles."""

    @property
    def model_name(self) -> str:
        """Return the configured embedding model name."""

    @property
    def dimension(self) -> int:
        """Return the dense vector dimension."""

    @property
    def distance_metric(self) -> DistanceMetric:
        """Return the distance metric expected by pgvector."""

    @property
    def normalized(self) -> bool:
        """Return whether vectors are normalized by the provider."""

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        """Return optional provider capabilities."""

    @property
    def batch_size(self) -> int:
        """Return the configured embedding batch size."""

    @property
    def retries(self) -> int:
        """Return the configured retry budget for retryable provider errors."""

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        """Return document embeddings for indexing."""

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        """Return query embeddings for retrieval."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one document embedding per input text for legacy consumers."""
