from __future__ import annotations

import logging

import pytest

from indexing.application.ports import IndexingPort
from indexing.application.use_cases.index_document import (
    IndexDocumentUseCase,
    IndexingRejectedError,
)
from indexing.domain.models import (
    IndexableDocument,
    IndexingProfile,
    IndexingResult,
    NormalizedArtifactRefs,
)


class RecordingIndexer(IndexingPort):
    def __init__(self) -> None:
        self.documents: list[IndexableDocument] = []

    async def index(self, document: IndexableDocument) -> IndexingResult:
        self.documents.append(document)
        return IndexingResult(
            document_id=document.document_id,
            profile=document.profile,
            indexed_parent_nodes=1,
            indexed_child_nodes=2,
            deleted_stale_nodes=0,
            warnings=[],
        )


def _document(*, status: str = "processed") -> IndexableDocument:
    return IndexableDocument(
        document_id="doc_123",
        source_relpath="manual/test.pdf",
        source_hash="a" * 64,
        document_status=status,
        artifacts=NormalizedArtifactRefs(
            markdown="manual/test.md",
            metadata="manual/test.metadata.json",
            pages="manual/test.pages.json",
            tables="manual/test.tables.json",
            forms="manual/test.forms.json",
        ),
        profile=IndexingProfile(
            profile_id="llama-first-local-v1",
            chunking_version="structure-aware-v1",
            embedding_provider="mock",
            embedding_model="deterministic",
            embedding_dimension=3,
            vector_store="memory",
            metadata_schema_version="2.0",
        ),
    )


@pytest.mark.anyio
async def test_index_document_use_case_sends_approved_bundle_to_indexing_port() -> None:
    indexer = RecordingIndexer()
    use_case = IndexDocumentUseCase(indexer=indexer)

    result = await use_case.index(_document())

    assert result.indexed_child_nodes == 2
    assert indexer.documents[0].document_id == "doc_123"
    assert indexer.documents[0].profile.profile_id == "llama-first-local-v1"


@pytest.mark.anyio
async def test_index_document_use_case_rejects_needs_review_by_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    indexer = RecordingIndexer()
    use_case = IndexDocumentUseCase(indexer=indexer)

    with pytest.raises(IndexingRejectedError, match="needs_review"):
        await use_case.index(_document(status="needs_review"))

    assert indexer.documents == []
    event_names = {
        record.event for record in caplog.records if hasattr(record, "event")
    }
    assert "indexing_document_rejected" in event_names


@pytest.mark.anyio
async def test_index_document_use_case_can_allow_needs_review_for_sandbox() -> None:
    indexer = RecordingIndexer()
    use_case = IndexDocumentUseCase(indexer=indexer, allow_needs_review=True)

    result = await use_case.index(_document(status="needs_review"))

    assert result.warnings == ["indexed_needs_review_document"]
    assert indexer.documents[0].document_status == "needs_review"
