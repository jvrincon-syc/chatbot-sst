"""Deterministic builders shared by the bundle-first test suites."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from embedding.application.bundle_builder import (
    EmbeddingBundleBuilder,
    EmbeddingBundleValidator,
)
from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
from embedding.application.run_service import (
    CreateEmbeddingRunRequest,
    CreateEmbeddingRunUseCase,
    EmbeddingRunExecutor,
)
from embedding.domain.models import ChunkBundleRef, EmbeddingProfile
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    FilesystemChunkBundleContentReader,
)
from embedding.infrastructure.in_memory.repositories import (
    InMemoryChunkBundleRepository,
    InMemoryEmbeddingBundleRepository,
    InMemoryEmbeddingProfileRepository,
    InMemoryEmbeddingRunRepository,
    InMemoryIndexingTargetRepository,
    InMemoryReadinessCheckRepository,
)
from indexing.application.bundle_first.activation import (
    ActivateIndexedBundleUseCase,
    RollbackIndexedBundleUseCase,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexEmbeddingBundleUseCase,
    IndexingRunExecutor,
    IndexingRunReconciler,
)
from indexing.domain.bundle_first import IndexingTarget
from indexing.infrastructure.in_memory.bundle_first import (
    InMemoryBundleVectorRepository,
    InMemoryIndexingNodeWriter,
    InMemoryIndexingRunDocumentRepository,
    InMemoryIndexingRunRepository,
)
from retrieval.application.query_embedding_service import QueryEmbeddingService
from retrieval.application.retrieval_service import (
    ActivateRetrievalProfileUseCase,
    CreateRetrievalProfileUseCase,
    RetrievalReadinessEvaluator,
    RetrievalSearchService,
    ValidateRetrievalUseCase,
)
from retrieval.infrastructure.in_memory.repositories import (
    InMemoryLexicalSearch,
    InMemoryParentExpansion,
    InMemoryRetrievalProfileRepository,
    InMemoryVectorSearch,
)


class NullTransactionManager:
    """Transaction manager for in-memory wiring."""

    def transaction(self):
        """Return a no-op scope."""

        return nullcontext()


MOCK_REVISION = "deterministic-v1"
DIMENSION = 8
DOCUMENT_ID = "doc_test_0001"
SOURCE_HASH = sha256(b"source").hexdigest()
CORPUS_VERSION = "phase1-test"
ARTIFACT_RELPATH = "unit/example.chunking_metadata.json"


def build_profile(**overrides: object) -> EmbeddingProfile:
    """Build a verified mock profile, overriding any semantic field."""

    values: dict[str, object] = {
        "profile_id": "test-mock-v1",
        "ingestion_origin": "local",
        "chunking_version": "structure-aware-v1",
        "provider": "mock",
        "model": "deterministic",
        "model_revision": MOCK_REVISION,
        "dimension": DIMENSION,
        "normalization": "none",
        "distance_metric": "cosine",
        "semantic_config": {},
        "vector_table": "idx_vec_test_mock_v1",
        "metadata_schema_version": "2.0",
        "config_hash": sha256(b"config").hexdigest(),
        "default_indexing_target_id": "target-idx-vec-test-mock-v1",
        "active": True,
        "document_enabled": True,
        "query_enabled": True,
        "compatibility_status": "verified",
    }
    values.update(overrides)
    profile = EmbeddingProfile.model_validate(values)
    if "configuration_fingerprint" not in overrides:
        profile = profile.model_copy(
            update={"configuration_fingerprint": profile.expected_fingerprint().value}
        )
    return profile


def build_target(**overrides: object) -> IndexingTarget:
    """Build the pgvector target matching :func:`build_profile`."""

    values: dict[str, object] = {
        "indexing_target_id": "target-idx-vec-test-mock-v1",
        "postgres_schema": "public",
        "vector_table": "idx_vec_test_mock_v1",
        "distance_ops": "vector_cosine_ops",
        "storage_schema_version": "idx-vec-v1",
        "active": True,
    }
    values.update(overrides)
    return IndexingTarget.model_validate(values)


def write_chunk_bundle(chunks_root: Path, *, child_count: int = 3) -> ChunkBundleRef:
    """Write a persisted chunk bundle and return its durable ledger row."""

    base = chunks_root / "unit" / "example"
    base.parent.mkdir(parents=True, exist_ok=True)
    parent_id = "parent-" + sha256(b"parent").hexdigest()
    parents = [
        {
            "chunk_id": parent_id,
            "document_id": DOCUMENT_ID,
            "profile_id": "local-structural-v1",
            "ordinal": 0,
            "text": "Parent text for the unit corpus.",
            "source_span": {"page_start": 1, "page_end": 1, "char_start": 0, "char_end": 32},
            "block_ids": ["block-1"],
        }
    ]
    children = [
        {
            "chunk_id": "child-" + sha256(f"child-{index}".encode()).hexdigest(),
            "parent_id": parent_id,
            "document_id": DOCUMENT_ID,
            "profile_id": "local-structural-v1",
            "ordinal": index,
            "context_prefix": "Section 1",
            "text": f"Child chunk number {index} about safety rules.",
            "source_span": {
                "page_start": 1,
                "page_end": 1,
                "char_start": index * 10,
                "char_end": index * 10 + 9,
            },
            "token_count": 9,
        }
        for index in range(child_count)
    ]
    _write_jsonl(Path(f"{base}.parent_chunks.jsonl"), parents)
    _write_jsonl(Path(f"{base}.child_chunks.jsonl"), children)
    bundle_fingerprint = "chunk-bundle-" + sha256(b"bundle").hexdigest()
    Path(f"{base}.chunking_metadata.json").write_text(
        json.dumps(
            {
                "bundle_fingerprint": bundle_fingerprint,
                "child_count": len(children),
                "corpus_version": CORPUS_VERSION,
                "document_id": DOCUMENT_ID,
                "normalized_relpath": "unit/example.md",
                "parent_count": len(parents),
                "profile_fingerprint": "chunking-profile-" + sha256(b"profile").hexdigest(),
                "profile_id": "local-structural-v1",
                "source_hash": SOURCE_HASH,
                "source_relpath": "unit/example.md",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return ChunkBundleRef(
        chunk_bundle_id=bundle_fingerprint,
        bundle_fingerprint=bundle_fingerprint,
        profile_id="local-structural-v1",
        profile_fingerprint="chunking-profile-" + sha256(b"profile").hexdigest(),
        corpus_version=CORPUS_VERSION,
        source_document_id=DOCUMENT_ID,
        artifact_relpath=ARTIFACT_RELPATH,
        parent_count=len(parents),
        child_count=len(children),
        status="legacy_unverified",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")




@dataclass
class PipelineStack:
    """Fully wired in-memory Embedding + Indexing + Retrieval stack."""

    profile: EmbeddingProfile
    chunk_bundle: ChunkBundleRef
    target: IndexingTarget
    profiles: InMemoryEmbeddingProfileRepository
    chunk_bundles: InMemoryChunkBundleRepository
    embedding_runs: InMemoryEmbeddingRunRepository
    bundles: InMemoryEmbeddingBundleRepository
    readiness_checks: InMemoryReadinessCheckRepository
    targets: InMemoryIndexingTargetRepository
    registry: DefaultEmbeddingEngineRegistry
    artifacts: FilesystemEmbeddingBundleArtifactStore
    content_reader: FilesystemChunkBundleContentReader
    builder: EmbeddingBundleBuilder
    create_embedding_run: CreateEmbeddingRunUseCase
    embedding_executor: EmbeddingRunExecutor
    indexing_runs: InMemoryIndexingRunRepository
    run_documents: InMemoryIndexingRunDocumentRepository
    nodes: InMemoryIndexingNodeWriter
    vectors: InMemoryBundleVectorRepository
    index_bundle: IndexEmbeddingBundleUseCase
    create_indexing_run: CreateIndexingRunUseCase
    indexing_executor: IndexingRunExecutor
    reconciler: IndexingRunReconciler
    retrieval_profiles: InMemoryRetrievalProfileRepository
    activate_bundle: ActivateIndexedBundleUseCase
    rollback_bundle: RollbackIndexedBundleUseCase
    query_embedding: QueryEmbeddingService
    vector_search: InMemoryVectorSearch
    search: RetrievalSearchService
    retrieval_readiness: RetrievalReadinessEvaluator
    activate_retrieval_profile: ActivateRetrievalProfileUseCase
    validate_retrieval: ValidateRetrievalUseCase
    create_retrieval_profile: CreateRetrievalProfileUseCase

    def run_embedding(self, *, idempotency_key: str = "embed-1") -> str:
        """Create and execute one embedding run; return the sealed bundle id."""

        run = self.create_embedding_run.execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id=self.chunk_bundle.chunk_bundle_id,
                profile_id=self.profile.profile_id,
            ),
            idempotency_key=idempotency_key,
        )
        completed = self.embedding_executor.execute(run.embedding_run_id)
        assert completed.status == "completed", completed.error_summary
        return str(completed.produced_embedding_bundle_id)

    def run_indexing(self, embedding_bundle_id: str, *, idempotency_key: str = "index-1") -> str:
        """Create and execute one indexing run; return the run id."""

        run = self.create_indexing_run.execute(
            request=CreateIndexingRunRequest(embedding_bundle_id=embedding_bundle_id),
            idempotency_key=idempotency_key,
        )
        completed = self.indexing_executor.execute(run.run_id)
        assert completed.status == "completed", completed.warnings
        return completed.run_id


def build_pipeline_stack(root: Path, *, child_count: int = 3) -> PipelineStack:
    """Wire the whole bundle-first pipeline on in-memory adapters."""

    profile = build_profile()
    target = build_target()
    chunk_bundle = write_chunk_bundle(root / "chunks", child_count=child_count)

    profiles = InMemoryEmbeddingProfileRepository([profile])
    chunk_bundles = InMemoryChunkBundleRepository([chunk_bundle])
    embedding_runs = InMemoryEmbeddingRunRepository()
    bundles = InMemoryEmbeddingBundleRepository()
    readiness_checks = InMemoryReadinessCheckRepository()
    targets = InMemoryIndexingTargetRepository([target])
    registry = DefaultEmbeddingEngineRegistry(environ={}, allow_mock=True)
    artifacts = FilesystemEmbeddingBundleArtifactStore(root=root / "embeddings")
    content_reader = FilesystemChunkBundleContentReader(chunks_root=root / "chunks")
    builder = EmbeddingBundleBuilder(
        bundles=bundles,
        artifacts=artifacts,
        validator=EmbeddingBundleValidator(artifacts=artifacts),
        readiness_checks=readiness_checks,
        batch_size=2,
    )
    indexing_runs = InMemoryIndexingRunRepository()
    run_documents = InMemoryIndexingRunDocumentRepository()
    nodes = InMemoryIndexingNodeWriter()
    vectors = InMemoryBundleVectorRepository()
    retrieval_profiles = InMemoryRetrievalProfileRepository()
    transactions = NullTransactionManager()

    index_bundle = IndexEmbeddingBundleUseCase(
        profiles=profiles,
        chunk_bundles=chunk_bundles,
        bundles=bundles,
        targets=targets,
        nodes=nodes,
        vectors=vectors,
        artifacts=artifacts,
        content_reader=content_reader,
        run_documents=run_documents,
        readiness_checks=readiness_checks,
        transactions=transactions,
    )
    query_embedding = QueryEmbeddingService(profiles=profiles, registry=registry)
    vector_search = InMemoryVectorSearch(vectors=vectors, nodes=nodes)
    lexical_search = InMemoryLexicalSearch(nodes=nodes, embedding_profile_id=profile.profile_id)
    parent_expansion = InMemoryParentExpansion(
        nodes=nodes,
        embedding_profile_id=profile.profile_id,
    )
    search = RetrievalSearchService(
        retrieval_profiles=retrieval_profiles,
        profiles=profiles,
        targets=targets,
        query_embedding=query_embedding,
        vector_search=vector_search,
        lexical_search=lexical_search,
        parent_expansion=parent_expansion,
    )
    retrieval_readiness = RetrievalReadinessEvaluator(
        retrieval_profiles=retrieval_profiles,
        profiles=profiles,
        targets=targets,
        vector_search=vector_search,
        query_embedding=query_embedding,
    )
    return PipelineStack(
        profile=profile,
        chunk_bundle=chunk_bundle,
        target=target,
        profiles=profiles,
        chunk_bundles=chunk_bundles,
        embedding_runs=embedding_runs,
        bundles=bundles,
        readiness_checks=readiness_checks,
        targets=targets,
        registry=registry,
        artifacts=artifacts,
        content_reader=content_reader,
        builder=builder,
        create_embedding_run=CreateEmbeddingRunUseCase(
            runs=embedding_runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            registry=registry,
        ),
        embedding_executor=EmbeddingRunExecutor(
            runs=embedding_runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            registry=registry,
            builder=builder,
            content_reader=content_reader,
        ),
        indexing_runs=indexing_runs,
        run_documents=run_documents,
        nodes=nodes,
        vectors=vectors,
        index_bundle=index_bundle,
        create_indexing_run=CreateIndexingRunUseCase(
            runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            index_use_case=index_bundle,
        ),
        indexing_executor=IndexingRunExecutor(
            runs=indexing_runs,
            index_use_case=index_bundle,
        ),
        reconciler=IndexingRunReconciler(runs=indexing_runs, run_documents=run_documents),
        retrieval_profiles=retrieval_profiles,
        activate_bundle=ActivateIndexedBundleUseCase(
            runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            targets=targets,
            vectors=vectors,
            artifacts=artifacts,
            retrieval_profiles=retrieval_profiles,
            readiness_checks=readiness_checks,
            transactions=transactions,
        ),
        rollback_bundle=RollbackIndexedBundleUseCase(
            bundles=bundles,
            profiles=profiles,
            targets=targets,
            vectors=vectors,
            retrieval_profiles=retrieval_profiles,
            transactions=transactions,
        ),
        query_embedding=query_embedding,
        vector_search=vector_search,
        search=search,
        retrieval_readiness=retrieval_readiness,
        activate_retrieval_profile=ActivateRetrievalProfileUseCase(
            retrieval_profiles=retrieval_profiles,
            readiness=retrieval_readiness,
            readiness_checks=readiness_checks,
        ),
        validate_retrieval=ValidateRetrievalUseCase(
            retrieval_profiles=retrieval_profiles,
            search=search,
            readiness_checks=readiness_checks,
        ),
        create_retrieval_profile=CreateRetrievalProfileUseCase(
            retrieval_profiles=retrieval_profiles,
            profiles=profiles,
            targets=targets,
        ),
    )
