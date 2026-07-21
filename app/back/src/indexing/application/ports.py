from __future__ import annotations

from typing import Protocol

from indexing.domain.models import IndexableDocument, IndexingResult


class IndexingPort(Protocol):
    async def index(self, document: IndexableDocument) -> IndexingResult:
        """Index a normalized, approved document."""
