from __future__ import annotations

from dataclasses import dataclass

from indexing.domain.models import IndexingProfile


class EmbeddingProviderUnavailableError(RuntimeError):
    """Embedding provider runtime is not configured."""


@dataclass(frozen=True)
class BgeEmbeddingProvider:
    profile: IndexingProfile

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderUnavailableError(
            "BGE embedding runtime is not configured for this branch"
        )
