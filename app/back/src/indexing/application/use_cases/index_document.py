from __future__ import annotations

import logging

from indexing.application.ports import IndexingPort
from core.logging.observability import (
    EventContext,
    EventStatus,
    ObservabilityDomain,
    ObservabilityEvent,
    emit_observability_event,
)
from indexing.domain.models import IndexableDocument, IndexingResult

logger = logging.getLogger(__name__)


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
            emit_observability_event(
                logger=logger,
                event=ObservabilityEvent(
                    event="indexing_document_rejected",
                    domain=ObservabilityDomain.INDEXING,
                    status=EventStatus.REJECTED,
                    message="Document rejected for indexing",
                    context=EventContext(
                        document_id=document.document_id,
                        profile_id=document.profile.profile_id,
                        provider=document.profile.embedding_provider,
                        capability="index",
                    ),
                    attributes={
                        "reason": "needs_review_without_approval",
                        "document_status": document.document_status,
                    },
                ),
            )
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
