from __future__ import annotations

from dataclasses import dataclass

from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import EmbeddingProviderUnavailableError


@dataclass(frozen=True)
class CohereEmbeddingProvider:
    profile: IndexingProfile

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderUnavailableError(
            "Cohere embedding runtime is not configured for this branch"
        )
