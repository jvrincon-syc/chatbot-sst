from __future__ import annotations

from typing import Protocol

from indexing.domain.models import IndexingProfile


class EmbeddingProvider(Protocol):
    profile: IndexingProfile

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text."""
