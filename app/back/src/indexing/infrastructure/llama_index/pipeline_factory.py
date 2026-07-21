from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from llama_index.core.schema import BaseNode

from ingestion.schemas.artifacts import MetadataArtifact, PagesArtifact
from ingestion.schemas.loader import load_artifact
from indexing.domain.models import IndexableDocument, IndexingResult
from indexing.infrastructure.embeddings.factory import EmbeddingFactory
from indexing.infrastructure.llama_index.cache import (
    InMemoryIngestionCache,
    IngestionCacheKey,
)
from indexing.infrastructure.llama_index.docstore import InMemoryDocStore
from indexing.infrastructure.llama_index.document_factory import (
    NormalizedDocumentFactory,
)
from indexing.infrastructure.llama_index.metadata_pipeline import (
    MetadataEnrichmentPipeline,
)
from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)
from indexing.infrastructure.llama_index.pgvector_store import InMemoryVectorStore


@dataclass(frozen=True)
class NormalizedBundleArtifacts:
    markdown: str
    metadata: MetadataArtifact
    pages: PagesArtifact
    processing_fingerprint: str


class BundleLoader(Protocol):
    def load(self, document: IndexableDocument) -> NormalizedBundleArtifacts:
        """Load normalized artifacts for an indexable document."""


class FilesystemBundleLoader:
    def __init__(self, *, normalized_root: Path) -> None:
        self._normalized_root = normalized_root

    def load(self, document: IndexableDocument) -> NormalizedBundleArtifacts:
        markdown = (self._normalized_root / document.artifacts.markdown).read_text(
            encoding="utf-8"
        )
        metadata_payload = json.loads(
            (self._normalized_root / document.artifacts.metadata).read_text(
                encoding="utf-8"
            )
        )
        pages_payload = json.loads(
            (self._normalized_root / document.artifacts.pages).read_text(
                encoding="utf-8"
            )
        )
        return NormalizedBundleArtifacts(
            markdown=markdown,
            metadata=load_artifact(metadata_payload, "metadata"),
            pages=load_artifact(pages_payload, "pages"),
            processing_fingerprint=document.source_hash,
        )


class LlamaIndexingPort:
    def __init__(
        self,
        *,
        bundle_loader: BundleLoader,
        docstore: InMemoryDocStore | None = None,
        vector_store: InMemoryVectorStore | None = None,
        cache: InMemoryIngestionCache | None = None,
        max_child_chars: int = 900,
    ) -> None:
        self._bundle_loader = bundle_loader
        self._docstore = docstore or InMemoryDocStore()
        self._vector_store = vector_store or InMemoryVectorStore()
        self._cache = cache or InMemoryIngestionCache()
        self._document_factory = NormalizedDocumentFactory()
        self._parser = StructureAwareNodeParser(max_child_chars=max_child_chars)
        self._metadata_pipeline = MetadataEnrichmentPipeline()

    async def index(self, document: IndexableDocument) -> IndexingResult:
        artifacts = self._bundle_loader.load(document)
        cache_key = IngestionCacheKey(
            document_id=document.document_id,
            source_hash=document.source_hash,
            profile_id=document.profile.profile_id,
            processing_fingerprint=artifacts.processing_fingerprint,
        )
        if self._cache.has(cache_key):
            return IndexingResult(
                document_id=document.document_id,
                profile=document.profile,
                indexed_parent_nodes=0,
                indexed_child_nodes=0,
                deleted_stale_nodes=0,
                warnings=["index_cache_hit"],
            )

        llama_document = self._document_factory.create_document(
            markdown=artifacts.markdown,
            metadata=artifacts.metadata,
            pages=artifacts.pages,
            profile=document.profile,
            processing_fingerprint=artifacts.processing_fingerprint,
        )
        nodes = self._metadata_pipeline.apply(self._parser.parse(llama_document))
        parent_nodes = [node for node in nodes if node.metadata.get("node_role") == "parent"]
        child_nodes = [node for node in nodes if node.metadata.get("node_role") == "child"]
        embeddings = EmbeddingFactory().create(document.profile).embed_texts(
            [node.text for node in child_nodes]
        )

        doc_snapshot = self._docstore.snapshot()
        vector_snapshot = self._vector_store.snapshot()
        try:
            deleted = self._docstore.delete_by_ref_doc_id(document.document_id)
            self._vector_store.delete_by_ref_doc_id(document.document_id)
            self._docstore.upsert_nodes(nodes)
            self._vector_store.upsert_nodes(child_nodes, embeddings)
        except Exception:
            self._docstore.restore(doc_snapshot)
            self._vector_store.restore(vector_snapshot)
            raise

        self._cache.record(cache_key)
        return IndexingResult(
            document_id=document.document_id,
            profile=document.profile,
            indexed_parent_nodes=len(parent_nodes),
            indexed_child_nodes=len(child_nodes),
            deleted_stale_nodes=deleted,
            warnings=[],
        )


def leaves(nodes: list[BaseNode]) -> list[BaseNode]:
    return [node for node in nodes if node.metadata.get("node_role") == "child"]
