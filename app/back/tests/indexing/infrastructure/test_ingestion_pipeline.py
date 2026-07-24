from __future__ import annotations

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.models import (
    ChunkBundle,
    ChunkingProfile,
    ChildChunk,
    ParentChunk,
    SourceSpan,
)
import pytest

from indexing.domain.models import (
    IndexableDocument,
    IndexingProfile,
    NormalizedArtifactRefs,
)
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.docstore import InMemoryDocStore
from indexing.infrastructure.llama_index.pipeline_factory import (
    LoadedChunkBundle,
    LlamaIndexingPort,
)
from indexing.infrastructure.llama_index.pgvector_store import (
    InMemoryVectorStore,
    VectorStoreWriteError,
)


class StaticBundleLoader:
    def load(self, document: IndexableDocument) -> LoadedChunkBundle:
        return LoadedChunkBundle(
            bundle=_bundle(document.document_id),
            corpus_version="phase1",
            normalized_relpath=document.artifacts.markdown,
        )


def _bundle(document_id: str) -> ChunkBundle:
    profile = ChunkingProfile.local_structural_v1()
    text = "Contenido SST para indexar."
    parent = ParentChunk.create(
        document_id=document_id,
        profile_id=profile.profile_id,
        ordinal=0,
        text=text,
        source_span=SourceSpan(
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=len(text),
        ),
        block_ids=("block-1",),
    )
    child = ChildChunk.create(
        document_id=document_id,
        profile_id=profile.profile_id,
        parent_id=parent.chunk_id,
        ordinal=0,
        text=text,
        source_span=SourceSpan(
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=len(text),
        ),
        token_start=0,
        token_end=4,
        token_count=4,
        overlap_previous_tokens=0,
        overlap_next_tokens=0,
        zero_overlap_reasons=frozenset({ZeroOverlapReason.DOCUMENT_START}),
    )
    return ChunkBundle(
        document_id=document_id,
        profile=profile,
        parents=(parent,),
        children=(child,),
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
        assert all(
            node.metadata["ingestion_origin"] == profile.ingestion_origin for node in nodes
        )
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

    def replace_document(
        self,
        *,
        document,
        ingestion_origin,
        artifact_fingerprint,
        corpus_version,
    ) -> None:
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
