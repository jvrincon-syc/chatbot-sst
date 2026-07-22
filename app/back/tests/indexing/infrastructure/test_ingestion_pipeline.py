from __future__ import annotations

import pytest

from ingestion.schemas.artifacts import MetadataArtifact, PageRecord, PagesArtifact
from indexing.domain.models import (
    IndexableDocument,
    IndexingProfile,
    NormalizedArtifactRefs,
)
from indexing.infrastructure.llama_index.docstore import InMemoryDocStore
from indexing.infrastructure.llama_index.pgvector_store import (
    InMemoryVectorStore,
    VectorStoreWriteError,
)
from indexing.infrastructure.llama_index.pipeline_factory import (
    LlamaIndexingPort,
    NormalizedBundleArtifacts,
)
from indexing.domain.profiles import ResolvedIndexingProfile


class StaticBundleLoader:
    def load(self, document: IndexableDocument) -> NormalizedBundleArtifacts:
        classification = type(
            "ClassificationStub",
            (),
            {"document_type": "manual", "topic": "SST", "subtopic": None},
        )()
        metadata = MetadataArtifact.model_construct(
            document_id=document.document_id,
            document_name="Manual",
            source_relpath=document.source_relpath,
            normalized_relpath=document.artifacts.markdown,
            classification=classification,
            page_count=1,
            extraction_method="llamaparse",
            source_hash=document.source_hash,
            corpus_version="phase1",
            pipeline_version="2.0.0",
            processing_status=document.document_status,
            review_reasons=[],
            warnings=[],
        )
        pages = PagesArtifact.model_construct(
            document_id=document.document_id,
            page_count=1,
            pages=[
                PageRecord.model_construct(
                    page_number=1,
                    text_normalized="Contenido SST",
                    blocks=[],
                )
            ],
        )
        return NormalizedBundleArtifacts(
            markdown="<!-- page: 1 -->\n\nContenido SST para indexar.",
            metadata=metadata,
            pages=pages,
            processing_fingerprint="fingerprint-1",
        )


class FailingVectorStore(InMemoryVectorStore):
    def upsert_nodes(self, nodes, embeddings) -> None:
        raise VectorStoreWriteError("vector failure")


class RecordingVectorRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def replace_document_vectors(
        self,
        *,
        document_id: str,
        profile: ResolvedIndexingProfile,
        nodes,
        embeddings,
    ) -> int:
        self.calls.append((document_id, profile.vector_table, len(nodes)))
        assert all(node.metadata["ingestion_origin"] == profile.ingestion_origin for node in nodes)
        return 0


class RecordingNodeRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def replace_document_nodes(self, *, document_id: str, nodes) -> int:
        self.calls.append((document_id, len(nodes)))
        return 0


class RecordingNormalizedDocumentRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def replace_document(self, *, document, ingestion_origin, artifact_fingerprint, corpus_version) -> None:
        self.calls.append((document.document_id, ingestion_origin, corpus_version))


class FakeProfileOrchestrator:
    def resolve(self, *, profile_id: str, ingestion_origin: str) -> ResolvedIndexingProfile:
        assert profile_id == "llama-first-local-v1"
        assert ingestion_origin == "local"
        return ResolvedIndexingProfile(
            profile_id=profile_id,
            ingestion_origin="local",
            chunking_version="structure-aware-v1",
            embedding_provider="mock",
            embedding_model="deterministic",
            embedding_dimension=3,
            distance_metric="cosine",
            vector_table="idx_vec_local_mock_v1",
            metadata_schema_version="2.0",
            active=True,
            config_hash="a" * 64,
        )


def _profile() -> IndexingProfile:
    return IndexingProfile(
        profile_id="llama-first-local-v1",
        chunking_version="structure-aware-v1",
        embedding_provider="mock",
        embedding_model="deterministic",
        embedding_dimension=3,
        vector_store="memory",
        metadata_schema_version="2.0",
    )


def _document(source_hash: str = "a" * 64) -> IndexableDocument:
    return IndexableDocument(
        document_id="doc_1",
        source_relpath="manual/doc.pdf",
        source_hash=source_hash,
        document_status="processed",
        artifacts=NormalizedArtifactRefs(
            markdown="manual/doc.md",
            metadata="manual/doc.metadata.json",
            pages="manual/doc.pages.json",
            tables="manual/doc.tables.json",
            forms="manual/doc.forms.json",
        ),
        profile=_profile(),
    )


@pytest.mark.anyio
async def test_llama_indexing_port_indexes_parents_and_child_vectors() -> None:
    docstore = InMemoryDocStore()
    vector_store = InMemoryVectorStore()
    indexer = LlamaIndexingPort(
        bundle_loader=StaticBundleLoader(),
        docstore=docstore,
        vector_store=vector_store,
    )

    result = await indexer.index(_document())

    assert result.indexed_parent_nodes == 1
    assert result.indexed_child_nodes == 1
    assert len(docstore.nodes_for_ref_doc_id("doc_1")) == 2
    assert len(vector_store.nodes_for_ref_doc_id("doc_1")) == 1


@pytest.mark.anyio
async def test_llama_indexing_port_replaces_nodes_for_reindexed_document() -> None:
    docstore = InMemoryDocStore()
    vector_store = InMemoryVectorStore()
    indexer = LlamaIndexingPort(
        bundle_loader=StaticBundleLoader(),
        docstore=docstore,
        vector_store=vector_store,
    )

    await indexer.index(_document("a" * 64))
    result = await indexer.index(_document("b" * 64))

    assert result.deleted_stale_nodes == 2
    assert len(docstore.nodes_for_ref_doc_id("doc_1")) == 2
    assert len(vector_store.nodes_for_ref_doc_id("doc_1")) == 1


@pytest.mark.anyio
async def test_llama_indexing_port_rolls_back_docstore_when_vector_store_fails() -> None:
    docstore = InMemoryDocStore()
    docstore.upsert_nodes([])
    indexer = LlamaIndexingPort(
        bundle_loader=StaticBundleLoader(),
        docstore=docstore,
        vector_store=FailingVectorStore(),
    )

    with pytest.raises(VectorStoreWriteError):
        await indexer.index(_document())

    assert docstore.nodes_for_ref_doc_id("doc_1") == []


@pytest.mark.anyio
async def test_llama_indexing_port_writes_profile_repositories_for_selected_lane() -> None:
    node_repository = RecordingNodeRepository()
    vector_repository = RecordingVectorRepository()
    normalized_repository = RecordingNormalizedDocumentRepository()
    indexer = LlamaIndexingPort(
        bundle_loader=StaticBundleLoader(),
        node_repository=node_repository,
        vector_repository=vector_repository,
        normalized_document_repository=normalized_repository,
        profile_orchestrator=FakeProfileOrchestrator(),
        storage_mode="postgres",
    )

    result = await indexer.index(_document())

    assert result.indexed_parent_nodes == 1
    assert result.indexed_child_nodes == 1
    assert normalized_repository.calls == [("doc_1", "local", "phase1")]
    assert node_repository.calls == [("doc_1", 2)]
    assert vector_repository.calls == [("doc_1", "idx_vec_local_mock_v1", 1)]
