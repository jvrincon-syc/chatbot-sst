from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from llama_index.core import Document
from llama_index.core.schema import BaseNode

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.errors import ChunkInvariantError
from chunking.domain.models import (
    ChunkBundle,
    ChunkingProfile,
    ChildChunk,
    OverlapSpan,
    ParentChunk,
    SourceSpan,
)
from indexing.application.repositories import (
    NodeRepository,
    NormalizedDocumentRepository,
    ProfileResolver,
    VectorRepository,
)
from indexing.domain.models import IndexableDocument, IndexingResult
from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile
from indexing.infrastructure.embeddings.factory import EmbeddingFactory
from indexing.infrastructure.llama_index.cache import (
    InMemoryIngestionCache,
    IngestionCacheKey,
)
from indexing.infrastructure.llama_index.docstore import InMemoryDocStore
from indexing.infrastructure.llama_index.metadata_pipeline import (
    MetadataEnrichmentPipeline,
)
from indexing.infrastructure.llama_index.node_parsers.structure_aware import (
    StructureAwareNodeParser,
)
from indexing.infrastructure.llama_index.pgvector_store import InMemoryVectorStore


logger = logging.getLogger(__name__)

_CANONICAL_CHUNKING_PROFILE = ChunkingProfile.local_structural_v1()
_DOCUMENT_EXCLUDED_EMBED_METADATA_KEYS = [
    "document_id",
    "ref_doc_id",
    "source_relpath",
    "source_hash",
    "normalized_relpath",
    "processing_fingerprint",
    "corpus_version",
    "pipeline_version",
    "processing_status",
    "review_reasons",
    "profile_id",
    "chunking_version",
    "chunking_profile_id",
    "bundle_fingerprint",
    "embedding_provider",
    "embedding_model",
    "embedding_dimension",
    "vector_store",
    "ingestion_origin",
    "distance_metric",
    "vector_table",
    "chunking_bundle",
]


@dataclass(frozen=True)
class LoadedChunkBundle:
    """Validated chunk bundle and the persisted provenance needed by indexing."""

    bundle: ChunkBundle
    corpus_version: str
    normalized_relpath: str


class BundleLoader(Protocol):
    def load(self, document: IndexableDocument) -> LoadedChunkBundle:
        """Load a validated chunk bundle for an approved normalized document."""


class FilesystemBundleLoader:
    """Load validated bundles from ``data/chunks`` or the configured chunk root."""

    def __init__(self, *, chunks_root: Path) -> None:
        self._chunks_root = chunks_root.resolve()

    def load(self, document: IndexableDocument) -> LoadedChunkBundle:
        normalized_relpath = Path(document.artifacts.markdown)
        base = (self._chunks_root / normalized_relpath.with_suffix("")).resolve()
        metadata_path = base.parent / f"{base.name}.chunking_metadata.json"
        parent_path = base.parent / f"{base.name}.parent_chunks.jsonl"
        child_path = base.parent / f"{base.name}.child_chunks.jsonl"

        for path in (metadata_path, parent_path, child_path):
            if not path.is_file():
                raise FileNotFoundError(f"chunk bundle artifact is missing: {path.name}")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        corpus_version = str(metadata.get("corpus_version") or "")
        if not corpus_version:
            raise ChunkInvariantError("chunk bundle metadata must include corpus_version")

        profile_id = str(metadata.get("profile_id") or "")
        if profile_id != _CANONICAL_CHUNKING_PROFILE.profile_id:
            raise ChunkInvariantError("unsupported chunking profile persisted in bundle")

        parents = tuple(
            self._parent_from_payload(payload)
            for payload in self._read_jsonl(parent_path)
        )
        children = tuple(
            self._child_from_payload(payload)
            for payload in self._read_jsonl(child_path)
        )
        bundle = ChunkBundle(
            document_id=document.document_id,
            profile=_CANONICAL_CHUNKING_PROFILE,
            parents=parents,
            children=children,
        )

        expected_profile_fingerprint = str(metadata.get("profile_fingerprint") or "")
        if expected_profile_fingerprint and expected_profile_fingerprint != bundle.profile.fingerprint:
            raise ChunkInvariantError("persisted profile fingerprint does not match bundle")

        expected_bundle_fingerprint = str(metadata.get("bundle_fingerprint") or "")
        if expected_bundle_fingerprint and expected_bundle_fingerprint != bundle.fingerprint:
            raise ChunkInvariantError("persisted bundle fingerprint does not match bundle")

        expected_parent_count = metadata.get("parent_count")
        expected_child_count = metadata.get("child_count")
        if expected_parent_count is not None and int(expected_parent_count) != len(parents):
            raise ChunkInvariantError("persisted parent count does not match bundle")
        if expected_child_count is not None and int(expected_child_count) != len(children):
            raise ChunkInvariantError("persisted child count does not match bundle")

        return LoadedChunkBundle(
            bundle=bundle,
            corpus_version=corpus_version,
            normalized_relpath=normalized_relpath.as_posix(),
        )

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ChunkInvariantError("chunk payload rows must be JSON objects")
            rows.append(payload)
        return rows

    def _parent_from_payload(self, payload: dict[str, Any]) -> ParentChunk:
        return ParentChunk(
            chunk_id=str(payload["chunk_id"]),
            document_id=str(payload["document_id"]),
            profile_id=str(payload["profile_id"]),
            ordinal=int(payload["ordinal"]),
            text=str(payload["text"]),
            source_span=self._source_span_from_payload(payload["source_span"]),
            block_ids=tuple(str(block_id) for block_id in payload["block_ids"]),
        )

    def _child_from_payload(self, payload: dict[str, Any]) -> ChildChunk:
        return ChildChunk(
            chunk_id=str(payload["chunk_id"]),
            document_id=str(payload["document_id"]),
            profile_id=str(payload["profile_id"]),
            parent_id=str(payload["parent_id"]),
            ordinal=int(payload["ordinal"]),
            text=str(payload["text"]),
            source_span=self._source_span_from_payload(payload["source_span"]),
            token_start=int(payload["token_start"]),
            token_end=int(payload["token_end"]),
            token_count=int(payload["token_count"]),
            overlap_previous_tokens=int(payload["overlap_previous_tokens"]),
            overlap_next_tokens=int(payload["overlap_next_tokens"]),
            overlap_previous_span=self._overlap_span_from_payload(
                payload.get("overlap_previous_span")
            ),
            overlap_next_span=self._overlap_span_from_payload(
                payload.get("overlap_next_span")
            ),
            context_prefix=str(payload.get("context_prefix") or ""),
            zero_overlap_reasons=frozenset(
                ZeroOverlapReason(reason)
                for reason in payload.get("zero_overlap_reasons", [])
            ),
            warnings=tuple(str(warning) for warning in payload.get("warnings", [])),
        )

    def _source_span_from_payload(self, payload: dict[str, Any]) -> SourceSpan:
        return SourceSpan(
            page_start=(
                int(payload["page_start"])
                if payload.get("page_start") is not None
                else None
            ),
            page_end=(
                int(payload["page_end"])
                if payload.get("page_end") is not None
                else None
            ),
            char_start=int(payload["char_start"]),
            char_end=int(payload["char_end"]),
        )

    def _overlap_span_from_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> OverlapSpan | None:
        if payload is None:
            return None
        return OverlapSpan(
            token_start=int(payload["token_start"]),
            token_end=int(payload["token_end"]),
        )


class LlamaIndexingPort:
    def __init__(
        self,
        *,
        bundle_loader: BundleLoader,
        docstore: InMemoryDocStore | None = None,
        vector_store: InMemoryVectorStore | None = None,
        cache: InMemoryIngestionCache | None = None,
        normalized_document_repository: NormalizedDocumentRepository | None = None,
        node_repository: NodeRepository | None = None,
        vector_repository: VectorRepository | None = None,
        profile_orchestrator: ProfileResolver | None = None,
        embedding_factory: EmbeddingFactory | None = None,
        storage_mode: Literal["memory", "postgres"] = "memory",
        ingestion_origin: IngestionOrigin = "local",
    ) -> None:
        self._bundle_loader = bundle_loader
        self._docstore = docstore or InMemoryDocStore()
        self._vector_store = vector_store or InMemoryVectorStore()
        self._cache = cache or InMemoryIngestionCache()
        self._normalized_document_repository = normalized_document_repository
        self._node_repository = node_repository
        self._vector_repository = vector_repository
        self._profile_orchestrator = profile_orchestrator
        self._embedding_factory = embedding_factory or EmbeddingFactory()
        self._storage_mode = storage_mode
        self._ingestion_origin = ingestion_origin
        self._metadata_pipeline = MetadataEnrichmentPipeline()
        self._parser = StructureAwareNodeParser()

    async def index(self, document: IndexableDocument) -> IndexingResult:
        loaded = self._bundle_loader.load(document)
        cache_key = IngestionCacheKey(
            document_id=document.document_id,
            source_hash=document.source_hash,
            profile_id=document.profile.profile_id,
            processing_fingerprint=loaded.bundle.fingerprint,
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

        resolved_profile = self._resolve_profile(document)
        llama_document = self._build_document(document=document, loaded=loaded)
        nodes = self._metadata_pipeline.apply(self._parser.parse(llama_document))
        nodes = _with_profile_metadata(nodes=nodes, profile=resolved_profile)
        parent_nodes = [
            node for node in nodes if node.metadata.get("node_role") == "parent"
        ]
        child_nodes = [
            node for node in nodes if node.metadata.get("node_role") == "child"
        ]
        embeddings = self._embedding_factory.create(document.profile).embed_documents(
            [node.text for node in child_nodes]
        ).vectors

        if self._storage_mode == "postgres":
            self._write_repositories(
                document=document,
                loaded=loaded,
                nodes=nodes,
                child_nodes=child_nodes,
                embeddings=embeddings,
                profile=resolved_profile,
            )
            self._cache.record(cache_key)
            return IndexingResult(
                document_id=document.document_id,
                profile=document.profile,
                indexed_parent_nodes=len(parent_nodes),
                indexed_child_nodes=len(child_nodes),
                deleted_stale_nodes=0,
                warnings=[],
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

    def _build_document(
        self,
        *,
        document: IndexableDocument,
        loaded: LoadedChunkBundle,
    ) -> Document:
        text = "\n\n".join(parent.text for parent in loaded.bundle.parents)
        metadata = {
            "document_id": document.document_id,
            "ref_doc_id": document.document_id,
            "source_relpath": document.source_relpath,
            "source_hash": document.source_hash,
            "normalized_relpath": document.artifacts.markdown,
            "processing_fingerprint": loaded.bundle.fingerprint,
            "corpus_version": loaded.corpus_version,
            "profile_id": document.profile.profile_id,
            "chunking_version": document.profile.chunking_version,
            "chunking_profile_id": loaded.bundle.profile.profile_id,
            "bundle_fingerprint": loaded.bundle.fingerprint,
            "chunking_bundle": loaded.bundle,
            "vector_store": document.profile.vector_store,
        }
        return Document(
            text=text,
            id_=document.document_id,
            metadata=metadata,
            excluded_embed_metadata_keys=list(_DOCUMENT_EXCLUDED_EMBED_METADATA_KEYS),
        )

    def _resolve_profile(self, document: IndexableDocument) -> ResolvedIndexingProfile:
        if self._storage_mode == "memory":
            return ResolvedIndexingProfile(
                profile_id=document.profile.profile_id,
                ingestion_origin=self._ingestion_origin,
                chunking_version=document.profile.chunking_version,
                embedding_provider=document.profile.embedding_provider,
                embedding_model=document.profile.embedding_model,
                embedding_dimension=document.profile.embedding_dimension,
                distance_metric="cosine",
                vector_table="idx_vec_memory",
                metadata_schema_version=document.profile.metadata_schema_version,
                active=True,
                config_hash="0" * 64,
            )
        if self._profile_orchestrator is None:
            raise ValueError("postgres storage requires profile_orchestrator")
        return self._profile_orchestrator.resolve(
            profile_id=document.profile.profile_id,
            ingestion_origin=self._ingestion_origin,
        )

    def _write_repositories(
        self,
        *,
        document: IndexableDocument,
        loaded: LoadedChunkBundle,
        nodes: list[BaseNode],
        child_nodes: list[BaseNode],
        embeddings: list[list[float]],
        profile: ResolvedIndexingProfile,
    ) -> None:
        if self._normalized_document_repository is None:
            raise ValueError("postgres storage requires normalized_document_repository")
        if self._node_repository is None:
            raise ValueError("postgres storage requires node_repository")
        if self._vector_repository is None:
            raise ValueError("postgres storage requires vector_repository")
        self._normalized_document_repository.replace_document(
            document=document,
            ingestion_origin=profile.ingestion_origin,
            artifact_fingerprint=loaded.bundle.fingerprint,
            corpus_version=loaded.corpus_version,
        )
        self._node_repository.replace_document_nodes(
            document_id=document.document_id,
            nodes=nodes,
        )
        self._vector_repository.replace_document_vectors(
            document_id=document.document_id,
            profile=profile,
            nodes=child_nodes,
            embeddings=embeddings,
        )


def leaves(nodes: list[BaseNode]) -> list[BaseNode]:
    return [node for node in nodes if node.metadata.get("node_role") == "child"]


def _with_profile_metadata(
    *,
    nodes: list[BaseNode],
    profile: ResolvedIndexingProfile,
) -> list[BaseNode]:
    return [
        node.model_copy(
            update={
                "metadata": {
                    **node.metadata,
                    "ingestion_origin": profile.ingestion_origin,
                    "distance_metric": profile.distance_metric,
                    "vector_table": profile.vector_table,
                }
            },
            deep=True,
        )
        for node in nodes
    ]
