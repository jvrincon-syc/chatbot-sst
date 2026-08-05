from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from pydantic import SecretStr

from indexing.application.embedding_provider import (
    EmbeddingBatch,
    EmbeddingCapabilities,
    EmbeddingProviderAuthenticationError,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderRateLimitError,
    EmbeddingProviderResponseError,
    EmbeddingProviderTimeoutError,
)
from indexing.domain.models import IndexingProfile
from indexing.domain.profiles import DistanceMetric
from indexing.infrastructure.embeddings.base import embedding_batch, validate_texts
from indexing.infrastructure.embeddings.settings import EmbeddingSettings


class VoyageRuntimeClient(Protocol):
    def embed(self, texts, **kwargs):
        """Embed texts with the Voyage SDK."""


VoyageClientFactory = Callable[[EmbeddingSettings], VoyageRuntimeClient]


@dataclass
class VoyageEmbeddingProvider:
    profile: IndexingProfile
    settings: EmbeddingSettings | None = None
    client_factory: VoyageClientFactory | None = None

    def __post_init__(self) -> None:
        self._settings = self.settings or EmbeddingSettings(provider="voyage")
        self._client: VoyageRuntimeClient | None = None

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
        return self._settings.distance_metric

    @property
    def normalized(self) -> bool:
        return True

    @property
    def capabilities(self) -> EmbeddingCapabilities:
        return EmbeddingCapabilities(supports_sparse=False, supports_multimodal=False)

    @property
    def batch_size(self) -> int:
        return self._settings.batch_size

    @property
    def retries(self) -> int:
        return self._settings.retries

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, input_type="document")

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        return self._embed(texts, input_type="query")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts).vectors

    def _embed(self, texts: list[str], *, input_type: str) -> EmbeddingBatch:
        batch_texts = validate_texts(texts)
        client = self._get_client()
        vectors: list[list[float]] = []
        for chunk in _chunks(batch_texts, self._settings.batch_size):
            try:
                response = client.embed(
                    chunk,
                    model=self.profile.embedding_model,
                    input_type=input_type,
                    output_dimension=self.profile.embedding_dimension,
                    truncation=True,
                )
            except Exception as error:
                raise _translate_voyage_error(error) from error
            chunk_vectors = getattr(response, "embeddings", None)
            if chunk_vectors is None:
                raise EmbeddingProviderResponseError(
                    "voyage response did not include embeddings"
                )
            vectors.extend(chunk_vectors)
        return embedding_batch(
            vectors=vectors,
            expected_count=len(batch_texts),
            profile=self.profile,
            distance_metric=self.distance_metric,
            normalized=self.normalized,
            capabilities=self.capabilities,
        )

    def _get_client(self) -> VoyageRuntimeClient:
        if self._settings.voyage_api_key is None:
            raise EmbeddingProviderAuthenticationError(
                "VOYAGE_API_KEY is required when the voyage embedding provider is active"
            )
        if self._client is None:
            factory = self.client_factory or _load_voyage_client
            self._client = factory(self._settings)
        return self._client


def _load_voyage_client(settings: EmbeddingSettings) -> VoyageRuntimeClient:
    try:
        import voyageai
    except ImportError as error:
        raise EmbeddingProviderConfigurationError(
            "voyageai is required for the voyage embedding provider"
        ) from error
    return voyageai.Client(api_key=_secret_value(settings.voyage_api_key))


def _secret_value(secret: SecretStr | None) -> str | None:
    return None if secret is None else secret.get_secret_value()


def _translate_voyage_error(error: Exception) -> Exception:
    error_name = error.__class__.__name__.lower()
    message = str(error).lower()
    if "rate" in error_name or "rate" in message or "429" in message:
        return EmbeddingProviderRateLimitError(
            "voyage embedding request was rate limited"
        )
    if "auth" in error_name or "unauthorized" in message or "401" in message:
        return EmbeddingProviderAuthenticationError("voyage authentication failed")
    if "timeout" in error_name or "timed out" in message:
        return EmbeddingProviderTimeoutError("voyage embedding request timed out")
    return EmbeddingProviderResponseError("voyage embedding request failed")


def _chunks(texts: list[str], batch_size: int) -> list[list[str]]:
    return [
        texts[index : index + batch_size]
        for index in range(0, len(texts), batch_size)
    ]
