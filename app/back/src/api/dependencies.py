"""Composition root for Embedding, Indexing and Retrieval.

Runtime modes are explicit. ``memory`` runs the in-memory adapters used by
dry-run, tests and local demos; ``postgres`` runs the durable adapters against a
configured database. Production selects ``postgres`` and never silently falls
back to memory: if PostgreSQL is required but unavailable, startup fails closed.
The observable HTTP contract is identical in both modes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

from core.consumer_scope import ConsumerScope
from core.feature_flags import FeatureFlags
from core.logging.logger import get_logger
from core.logging.observability import (
    EventStatus,
    ObservabilityDomain,
)
from embedding.application.events import emit_pipeline_event
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
from embedding.infrastructure.filesystem.chunk_bundle_catalog import (
    FilesystemChunkBundleCatalogRepository,
    HybridChunkBundleRepository,
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
    SearchRetrievalUseCase,
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


logger = get_logger(__name__)

PersistenceMode = Literal["memory", "postgres"]


class NullTransactionManager:
    """Transaction manager used when no database connection is configured."""

    def transaction(self):
        """Return a no-op scope."""

        return nullcontext()


class PostgresUnavailableAtStartup(RuntimeError):
    """Production requested PostgreSQL but no usable connection was available.

    Raised instead of silently downgrading to in-memory persistence.
    """


@dataclass
class PipelineServices:
    """Everything the HTTP layer needs, already wired."""

    feature_flags: FeatureFlags
    consumer_scope: ConsumerScope
    persistence_mode: PersistenceMode
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
    retrieval_search: SearchRetrievalUseCase
    connection: object | None = None

    def close(self) -> None:
        """Drain both bounded executors and close the database connection."""

        self.embedding_executor.close()
        self.indexing_executor.close()
        if self.connection is not None:
            close = getattr(self.connection, "close", None)
            if callable(close):
                close()


def build_pipeline_services(
    *,
    chunks_root: Path,
    embeddings_root: Path,
    connection: object | None = None,
    feature_flags: FeatureFlags | None = None,
    consumer_scope: ConsumerScope | None = None,
    allow_mock_engine: bool = False,
    seed_profiles: Iterable[EmbeddingProfile] = (),
    seed_targets: Iterable[IndexingTarget] = (),
    seed_chunk_bundles: Iterable[ChunkBundleRef] = (),
    lexical_profile_id: str = "",
) -> PipelineServices:
    """Wire the whole bundle-first surface on PostgreSQL or on memory."""

    flags = feature_flags or FeatureFlags.from_env()
    scope = consumer_scope or ConsumerScope.from_env()
    persistence_mode: PersistenceMode = "postgres" if connection is not None else "memory"
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
        lexical_search: object = InMemoryLexicalSearch(nodes=nodes)
        parent_expansion: object = InMemoryParentExpansion(nodes=nodes)
    else:
        profiles = PostgresEmbeddingProfileRepository(connection)
        targets = PostgresIndexingTargetRepository(connection)
        chunk_bundles = HybridChunkBundleRepository(
            primary=PostgresChunkBundleRepository(connection),
            filesystem=FilesystemChunkBundleCatalogRepository(chunks_root=chunks_root),
        )
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
        lexical_search = PostgresLexicalSearch(connection)
        parent_expansion = PostgresParentExpansion(connection)

    readiness_evaluator = EmbeddingIndexingReadinessEvaluator(targets=targets)
    builder = EmbeddingBundleBuilder(
        bundles=bundles,
        artifacts=artifacts,
        validator=EmbeddingBundleValidator(artifacts=artifacts),
        readiness_checks=readiness_checks,
        readiness_evaluator=readiness_evaluator,
    )
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
        consumer_scope=scope,
        persistence_mode=persistence_mode,
        connection=connection,
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
            connection=connection,
        ),
        embedding_executor=EmbeddingRunExecutor(
            runs=embedding_runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            registry=registry,
            builder=builder,
            content_reader=content_reader,
            connection=connection,
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
        retrieval_search=SearchRetrievalUseCase(
            retrieval_profiles=retrieval_profiles,
            search=search,
        ),
    )


def _resolve_persistence_mode(environ: Mapping[str, str]) -> PersistenceMode:
    """Resolve the requested persistence mode from the environment.

    ``SST_PERSISTENCE_MODE`` wins when set to ``memory`` or ``postgres``. When it
    is unset, PostgreSQL is selected if a DSN is configured, otherwise memory.
    """

    requested = (environ.get("SST_PERSISTENCE_MODE") or "").strip().lower()
    if requested in ("memory", "postgres"):
        return requested  # type: ignore[return-value]
    if requested:
        raise ValueError(
            f"SST_PERSISTENCE_MODE must be 'memory' or 'postgres', got {requested!r}"
        )
    return "postgres" if (environ.get("SST_POSTGRES_DSN") or "").strip() else "memory"


def _open_postgres_connection(dsn: str) -> object:
    """Open a psycopg2 connection, failing closed on any driver error."""

    try:
        import psycopg2
        from psycopg2.extensions import parse_dsn
    except ImportError as error:  # pragma: no cover - driver always installed
        raise PostgresUnavailableAtStartup(
            "psycopg2 is not installed but postgres persistence was requested"
        ) from error
    try:
        return psycopg2.connect(**parse_dsn(dsn))
    except Exception as error:  # noqa: BLE001 - startup boundary, sanitized below
        raise PostgresUnavailableAtStartup(
            f"could not connect to PostgreSQL ({type(error).__name__})"
        ) from error


def build_pipeline_services_from_env(
    *,
    chunks_root: Path,
    embeddings_root: Path,
    environ: Mapping[str, str] | None = None,
    allow_mock_engine: bool = False,
) -> PipelineServices:
    """Build the pipeline the way the production GUI server should.

    The persistence mode is explicit (``SST_PERSISTENCE_MODE`` or the presence of
    ``SST_POSTGRES_DSN``). In ``postgres`` mode the durable profiles, targets and
    repositories come from the database; there is no silent fallback to memory.
    Startup observability records the selected mode and the loaded profile and
    target counts so a degraded composition is never invisible.
    """

    env = os.environ if environ is None else environ
    mode = _resolve_persistence_mode(env)
    flags = FeatureFlags.from_env(env)

    connection: object | None = None
    if mode == "postgres":
        dsn = (env.get("SST_POSTGRES_DSN") or "").strip()
        if not dsn:
            raise PostgresUnavailableAtStartup(
                "postgres persistence was requested but SST_POSTGRES_DSN is empty"
            )
        connection = _open_postgres_connection(dsn)

    services = build_pipeline_services(
        chunks_root=chunks_root,
        embeddings_root=embeddings_root,
        connection=connection,
        feature_flags=flags,
        allow_mock_engine=allow_mock_engine,
    )
    _emit_startup_observability(services)
    return services


def _emit_startup_observability(services: PipelineServices) -> None:
    """Emit a safe, structured startup event describing the composition."""

    overview: dict[str, object] = {}
    try:
        overview = services.indexing_read_service.overview()
    except Exception:  # noqa: BLE001 - observability must never block startup
        logger.warning("startup_overview_unavailable", extra={"stage": "backend"})

    emit_pipeline_event(
        logger=logger,
        domain=ObservabilityDomain.BACKEND,
        event="pipeline_composition_ready",
        status=EventStatus.COMPLETED,
        message="Pipeline composition ready",
        capability="startup",
        attributes={
            "persistence_mode": services.persistence_mode,
            "embedding_v2": services.feature_flags.embedding_v2,
            "indexing_bundle_first": services.feature_flags.indexing_bundle_first,
            "retrieval_v1": services.feature_flags.retrieval_v1,
            "consumer_scope_type": services.consumer_scope.scope_type,
        },
        metrics={
            "profiles": int(overview.get("profiles", 0) or 0),
            "verified_profiles": int(overview.get("verified_profiles", 0) or 0),
            "targets": int(overview.get("targets", 0) or 0),
            "active_targets": int(overview.get("active_targets", 0) or 0),
        },
    )
