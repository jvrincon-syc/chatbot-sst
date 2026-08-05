from __future__ import annotations

from dataclasses import dataclass

from indexing.application.embedding_provider import EmbeddingBatch
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import EmbeddingProviderUnavailableError


@dataclass(frozen=True)
class CohereEmbeddingProvider:
    profile: IndexingProfile

    @property
    def retries(self) -> int:
        return 0

    def embed_documents(self, texts: list[str]) -> EmbeddingBatch:
        raise EmbeddingProviderUnavailableError(
            "Cohere embedding runtime is not configured for this branch"
        )

    def embed_queries(self, texts: list[str]) -> EmbeddingBatch:
        raise EmbeddingProviderUnavailableError(
            "Cohere embedding runtime is not configured for this branch"
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderUnavailableError(
            "Cohere embedding runtime is not configured for this branch"
        )
