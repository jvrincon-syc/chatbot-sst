"""Composition root for Embedding, Indexing and Retrieval.

PostgreSQL stays opt-in: without a connection the whole surface runs on the
in-memory adapters, which is what dry-run, tests and local development use. The
observable HTTP contract is identical in both modes.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from core.feature_flags import FeatureFlags
from embedding.application.bundle_builder import (
    EmbeddingBundleBuilder,
    EmbeddingBundleValidator,
    EmbeddingIndexingReadinessEvaluator,
)
from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
from embedding.application.read_service import EmbeddingReadService
from embedding.application.run_service import (
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
from embedding.infrastructure.postgres.repositories import (
    PostgresChunkBundleRepository,
    PostgresEmbeddingBundleRepository,
    PostgresEmbeddingProfileRepository,
    PostgresEmbeddingRunRepository,
    PostgresIndexingTargetRepository,
    PostgresReadinessCheckRepository,
)
from indexing.application.bundle_first.activation import (
    ActivateIndexedBundleUseCase,
    RollbackIndexedBundleUseCase,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunUseCase,
    IndexEmbeddingBundleUseCase,
    IndexingRunExecutor,
    IndexingRunReconciler,
)
from indexing.application.bundle_first.read_service import IndexingReadService
from indexing.domain.bundle_first import IndexingTarget
from indexing.infrastructure.in_memory.bundle_first import (
    InMemoryBundleVectorRepository,
    InMemoryIndexingNodeWriter,
    InMemoryIndexingRunDocumentRepository,
    InMemoryIndexingRunRepository,
)
from indexing.infrastructure.postgres.bundle_first import (
    PostgresIndexingNodeWriter,
    PostgresIndexingRunDocumentRepository,
    PostgresIndexingRunRepository,
    PsycopgTransactionManager,
)
from indexing.infrastructure.postgres.vector_repository import PostgresVectorRepository
from retrieval.application.query_embedding_service import QueryEmbeddingService
from retrieval.application.retrieval_service import (
    ActivateRetrievalProfileUseCase,
    CreateRetrievalProfileUseCase,
    GetRetrievalProfileStatusUseCase,
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
from retrieval.infrastructure.postgres.repositories import (
    PostgresLexicalSearch,
    PostgresParentExpansion,
    PostgresRetrievalProfileRepository,
    PostgresVectorSearch,
)


class NullTransactionManager:
    """Transaction manager used when no database connection is configured."""

    def transaction(self):
        """Return a no-op scope."""

        return nullcontext()


@dataclass
class PipelineServices:
    """Everything the HTTP layer needs, already wired."""

    feature_flags: FeatureFlags
    embedding_read_service: EmbeddingReadService
    embedding_create_run: CreateEmbeddingRunUseCase
    embedding_executor: EmbeddingRunExecutor
    indexing_read_service: IndexingReadService
    indexing_create_run: CreateIndexingRunUseCase
    indexing_executor: IndexingRunExecutor
    indexing_reconciler: IndexingRunReconciler
    indexing_activate: ActivateIndexedBundleUseCase
    indexing_rollback: RollbackIndexedBundleUseCase
    retrieval_profiles: object
    retrieval_create_profile: CreateRetrievalProfileUseCase
    retrieval_activate_profile: ActivateRetrievalProfileUseCase
    retrieval_profile_status: GetRetrievalProfileStatusUseCase
    retrieval_validate: ValidateRetrievalUseCase
    retrieval_search: RetrievalSearchService

    def close(self) -> None:
        """Drain both bounded executors."""

        self.embedding_executor.close()
        self.indexing_executor.close()


def build_pipeline_services(
    *,
    chunks_root: Path,
    embeddings_root: Path,
    connection: object | None = None,
    feature_flags: FeatureFlags | None = None,
    allow_mock_engine: bool = False,
    seed_profiles: Iterable[EmbeddingProfile] = (),
    seed_targets: Iterable[IndexingTarget] = (),
    seed_chunk_bundles: Iterable[ChunkBundleRef] = (),
    lexical_profile_id: str = "",
) -> PipelineServices:
    """Wire the whole bundle-first surface on PostgreSQL or on memory."""

    flags = feature_flags or FeatureFlags.from_env()
    registry = DefaultEmbeddingEngineRegistry(allow_mock=allow_mock_engine)
    artifacts = FilesystemEmbeddingBundleArtifactStore(root=embeddings_root)
    content_reader = FilesystemChunkBundleContentReader(chunks_root=chunks_root)

    if connection is None:
        profiles: object = InMemoryEmbeddingProfileRepository(seed_profiles)
        targets: object = InMemoryIndexingTargetRepository(seed_targets)
        chunk_bundles: object = InMemoryChunkBundleRepository(seed_chunk_bundles)
        embedding_runs: object = InMemoryEmbeddingRunRepository()
        bundles: object = InMemoryEmbeddingBundleRepository()
        readiness_checks: object = InMemoryReadinessCheckRepository()
        indexing_runs: object = InMemoryIndexingRunRepository()
        run_documents: object = InMemoryIndexingRunDocumentRepository()
        nodes: object = InMemoryIndexingNodeWriter()
        vectors: object = InMemoryBundleVectorRepository()
        retrieval_profiles: object = InMemoryRetrievalProfileRepository()
        transactions: object = NullTransactionManager()
        vector_search: object = InMemoryVectorSearch(vectors=vectors, nodes=nodes)
        lexical_search: object = InMemoryLexicalSearch(
            nodes=nodes,
            embedding_profile_id=lexical_profile_id,
        )
        parent_expansion: object = InMemoryParentExpansion(
            nodes=nodes,
            embedding_profile_id=lexical_profile_id,
        )
    else:
        profiles = PostgresEmbeddingProfileRepository(connection)
        targets = PostgresIndexingTargetRepository(connection)
        chunk_bundles = PostgresChunkBundleRepository(connection)
        embedding_runs = PostgresEmbeddingRunRepository(connection)
        bundles = PostgresEmbeddingBundleRepository(connection)
        readiness_checks = PostgresReadinessCheckRepository(connection)
        indexing_runs = PostgresIndexingRunRepository(connection)
        run_documents = PostgresIndexingRunDocumentRepository(connection)
        nodes = PostgresIndexingNodeWriter(connection)
        vectors = PostgresVectorRepository(connection)
        retrieval_profiles = PostgresRetrievalProfileRepository(connection)
        transactions = PsycopgTransactionManager(connection)
        vector_search = PostgresVectorSearch(connection)
        lexical_search = PostgresLexicalSearch(
            connection,
            embedding_profile_id=lexical_profile_id,
        )
        parent_expansion = PostgresParentExpansion(
            connection,
            embedding_profile_id=lexical_profile_id,
        )

    builder = EmbeddingBundleBuilder(
        bundles=bundles,
        artifacts=artifacts,
        validator=EmbeddingBundleValidator(artifacts=artifacts),
        readiness_checks=readiness_checks,
    )
    readiness_evaluator = EmbeddingIndexingReadinessEvaluator(targets=targets)
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
    return PipelineServices(
        feature_flags=flags,
        embedding_read_service=EmbeddingReadService(
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            runs=embedding_runs,
            bundles=bundles,
            readiness_checks=readiness_checks,
            registry=registry,
            readiness_evaluator=readiness_evaluator,
        ),
        embedding_create_run=CreateEmbeddingRunUseCase(
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
        indexing_read_service=IndexingReadService(
            runs=indexing_runs,
            run_documents=run_documents,
            targets=targets,
            profiles=profiles,
            bundles=bundles,
            vectors=vectors,
            bundle_first_enabled=flags.indexing_bundle_first,
        ),
        indexing_create_run=CreateIndexingRunUseCase(
            runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            index_use_case=index_bundle,
        ),
        indexing_executor=IndexingRunExecutor(
            runs=indexing_runs,
            index_use_case=index_bundle,
        ),
        indexing_reconciler=IndexingRunReconciler(
            runs=indexing_runs,
            run_documents=run_documents,
        ),
        indexing_activate=ActivateIndexedBundleUseCase(
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
        indexing_rollback=RollbackIndexedBundleUseCase(
            bundles=bundles,
            profiles=profiles,
            targets=targets,
            vectors=vectors,
            retrieval_profiles=retrieval_profiles,
            transactions=transactions,
        ),
        retrieval_profiles=retrieval_profiles,
        retrieval_create_profile=CreateRetrievalProfileUseCase(
            retrieval_profiles=retrieval_profiles,
            profiles=profiles,
            targets=targets,
        ),
        retrieval_activate_profile=ActivateRetrievalProfileUseCase(
            retrieval_profiles=retrieval_profiles,
            readiness=retrieval_readiness,
            readiness_checks=readiness_checks,
        ),
        retrieval_profile_status=GetRetrievalProfileStatusUseCase(
            retrieval_profiles=retrieval_profiles,
            profiles=profiles,
            registry_status=query_embedding,
            readiness=retrieval_readiness,
        ),
        retrieval_validate=ValidateRetrievalUseCase(
            retrieval_profiles=retrieval_profiles,
            search=search,
            readiness_checks=readiness_checks,
        ),
        retrieval_search=search,
    )
