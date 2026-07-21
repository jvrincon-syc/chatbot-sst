from __future__ import annotations

from indexing.application.ports import IndexingPort
from indexing.domain.models import IndexableDocument, IndexingResult


class IndexingRejectedError(ValueError):
    """Document is not eligible for indexing under the current policy."""


class IndexDocumentUseCase:
    def __init__(
        self,
        *,
        indexer: IndexingPort,
        allow_needs_review: bool = False,
    ) -> None:
        self._indexer = indexer
        self._allow_needs_review = allow_needs_review

    async def index(self, document: IndexableDocument) -> IndexingResult:
        if document.document_status == "needs_review" and not self._allow_needs_review:
            raise IndexingRejectedError(
                "needs_review documents are not indexed outside sandbox mode"
            )

        result = await self._indexer.index(document)
        if document.document_status == "needs_review":
            return result.model_copy(
                update={
                    "warnings": [
                        *result.warnings,
                        "indexed_needs_review_document",
                    ]
                }
            )
        return result
