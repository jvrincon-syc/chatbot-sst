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
from typing import Literal, TYPE_CHECKING

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


if TYPE_CHECKING:
    from rag_platform.application.services import RagPlatformServices


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
    # RAG platform admin services (Fase 6). Only wired when the
    # ``rag_platform_v1`` flag is on; ``None`` keeps the legacy surface untouched.
    rag_platform_build: object | None = None
    rag_platform_publish: object | None = None
    rag_platform_rebuild: object | None = None
    rag_platform_draft: object | None = None
    rag_platform_validate: object | None = None
    # Task 3: superficie tipada de proyectos/configuración (``RagPlatformServices``).
    # Task 4 la extenderá con variantes/releases; ``None`` deja el legacy intacto.
    rag_platform: RagPlatformServices | None = None

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
    services = PipelineServices(
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
    # RAG platform admin lane (Fase 6): wired only behind the flag, never touching
    # the legacy retrieval services already built above.
    if flags.rag_platform_v1:
        platform = _build_rag_platform_services(
            connection=connection,
            data_root=_platform_data_root(chunks_root),
            transactions=transactions,
            indexing_runs=indexing_runs,
            bundles=bundles,
            profiles=profiles,
            index_bundle=index_bundle,
            run_documents=run_documents,
        )
        services.rag_platform = platform
        # Compat legacy: los aliases apuntan a la misma composición tipada.
        services.rag_platform_build = platform.build_release
        services.rag_platform_publish = platform.publish_release
        services.rag_platform_rebuild = platform.rebuild_platform
        services.rag_platform_draft = platform.create_release_draft
        services.rag_platform_validate = platform.validate_release
    return services


def _build_rag_platform_services(
    *,
    connection: object | None,
    data_root: Path,
    transactions: object,
    indexing_runs: object,
    bundles: object,
    profiles: object,
    index_bundle: object,
    run_documents: object,
) -> "RagPlatformServices":
    """Cablea la superficie tipada única de plataforma para Fase 7 (Task 3 + Task 4).

    Un mismo repositorio de proyectos satisface ``ProjectRepository`` y
    ``ProjectConfigurationRepository`` (lectura version-aware por versión). Sin
    conexión usa adaptadores in-memory; con conexión, Postgres. Variantes,
    snapshots y releases se cablean sobre el **mismo** ``RagPlatformServices``, no
    una segunda superficie. Los aliases legacy de ``PipelineServices`` apuntan a
    estas mismas instancias para no recomponer una lane paralela.
    """

    import uuid

    from rag_platform.application.corpus_snapshot_service import (
        CreateCorpusSnapshotUseCase,
    )
    from rag_platform.application.project_configuration_service import (
        CreateProjectConfigurationVersionUseCase,
        GetProjectConfigurationUseCase,
        GetProjectConfigurationVersionUseCase,
    )
    from rag_platform.application.project_query_service import (
        GetProjectUseCase,
        ListChunkingProfilesUseCase,
        ListProcessingProfilesUseCase,
        ListProjectsUseCase,
        UpdateProjectMetadataUseCase,
    )
    from rag_platform.application.project_service import CreateProjectUseCase
    from rag_platform.application.publication_service import PublishRagReleaseUseCase
    from rag_platform.application.recipe_service import CreateRagVariantUseCase
    from rag_platform.application.release_build_service import BuildRagReleaseUseCase
    from rag_platform.application.release_query_service import (
        GetReleaseUseCase,
        ListProjectReleasesUseCase,
    )
    from rag_platform.application.release_retirement_service import (
        RetireRagReleaseUseCase,
    )
    from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
    from rag_platform.application.release_validator import ValidateRagReleaseUseCase
    from rag_platform.application.services import RagPlatformServices
    from rag_platform.application.variant_matrix_service import (
        CreateRagVariantFromMatrixCellUseCase,
        GetVariantMatrixUseCase,
    )
    from rag_platform.application.variant_query_service import (
        ListProjectVariantsUseCase,
    )
    from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy
    from rag_platform.infrastructure.storage.project_storage import (
        ProjectStorageResolver,
    )

    access_policy = AllowAllAccessPolicy()
    storage_roots = ProjectStorageResolver(data_root)

    def _release_id_factory() -> object:
        from rag_platform.domain.identity import IdentityKind, PlatformId

        return PlatformId(
            kind=IdentityKind.RAG_RELEASE, value="ragr_" + uuid.uuid4().hex[:16]
        )

    if connection is None:
        """eliminstar el in memory y reemplazar por postgres, pero por ahora se mantiene para pruebas y demos locales"""
        from embedding.infrastructure.in_memory.repositories import (
            InMemoryEmbeddingProfileRepository,
        )
        from rag_platform.infrastructure.in_memory.release_build_resolver import (
            InMemoryRevisionArtifactResolver,
        )
        from rag_platform.infrastructure.in_memory.repositories import (
            InMemoryChunkingProfileRepository,
            InMemoryCorpusSnapshotRepository,
            InMemoryProcessingProfileRepository,
            InMemoryProjectRepository,
            InMemoryRagBuildRunRepository,
            InMemoryRagVariantRepository,
            InMemorySourceDocumentRepository,
            InMemoryTargetBindingResolver,
        )
        from rag_platform.infrastructure.in_memory.release_repositories import (
            InMemoryRagReleaseMembershipRepository,
            InMemoryRagReleaseRepository,
        )

        """ a futuro eliminacion del in memory y reemplazo por postgres, pero por ahora se mantiene para pruebas y demos locales """
        projects: object = InMemoryProjectRepository()
        processing: object = InMemoryProcessingProfileRepository()
        chunking: object = InMemoryChunkingProfileRepository()
        variants: object = InMemoryRagVariantRepository()
        releases: object = InMemoryRagReleaseRepository()
        snapshots: object = InMemoryCorpusSnapshotRepository()
        documents: object = InMemorySourceDocumentRepository()
        embedding_profiles: object = InMemoryEmbeddingProfileRepository()
        bindings: object = InMemoryTargetBindingResolver()
        memberships: object = InMemoryRagReleaseMembershipRepository()
        configuration_versions: object = projects
        configuration_fingerprints: object = projects
        build_ledger: object = InMemoryRagBuildRunRepository()
        revision_resolver: object = InMemoryRevisionArtifactResolver()
    else:
        from embedding.infrastructure.postgres.repositories import (
            PostgresEmbeddingProfileRepository,
        )
        from rag_platform.infrastructure.postgres.artifact_repositories import (
            PostgresRagBuildRunRepository,
        )
        from rag_platform.infrastructure.postgres.document_repositories import (
            PostgresCorpusSnapshotRepository,
            PostgresSourceDocumentRepository,
        )
        from rag_platform.infrastructure.postgres.project_repositories import (
            PostgresChunkingProfileRepository,
            PostgresProcessingProfileRepository,
            PostgresProjectConfigurationFingerprintReader,
            PostgresProjectRepository,
            PostgresRagVariantRepository,
            PostgresTargetBindingResolver,
        )
        from rag_platform.infrastructure.postgres.release_repositories import (
            PostgresRagReleaseMembershipRepository,
            PostgresRagReleaseRepository,
        )
        from rag_platform.infrastructure.release_build_resolver import (
            PostgresRevisionArtifactResolver,
        )

        projects = PostgresProjectRepository(connection)
        processing = PostgresProcessingProfileRepository(connection)
        chunking = PostgresChunkingProfileRepository(connection)
        variants = PostgresRagVariantRepository(connection)
        releases = PostgresRagReleaseRepository(connection)
        snapshots = PostgresCorpusSnapshotRepository(connection)
        documents = PostgresSourceDocumentRepository(connection)
        embedding_profiles = PostgresEmbeddingProfileRepository(connection)
        bindings = PostgresTargetBindingResolver(connection)
        memberships = PostgresRagReleaseMembershipRepository(connection)
        configuration_versions = projects
        configuration_fingerprints = PostgresProjectConfigurationFingerprintReader(
            connection
        )
        build_ledger = PostgresRagBuildRunRepository(connection)
        revision_resolver = PostgresRevisionArtifactResolver(
            connection=connection,
            data_root=data_root,
        )

    variant_matrix = GetVariantMatrixUseCase(
        projects=projects,
        processing_profiles=processing,
        chunking_profiles=chunking,
    )
    create_variant = CreateRagVariantUseCase(
        variants=variants,
        processing_profiles=processing,
        chunking_profiles=chunking,
        embedding_profiles=embedding_profiles,
        target_bindings=bindings,
        access_policy=access_policy,
    )
    release_draft = CreateRagReleaseDraftUseCase(
        variants=variants,
        snapshots=snapshots,
        bindings=bindings,
        releases=releases,
        configuration_versions=configuration_versions,
        release_id_factory=_release_id_factory,
        logger=get_logger("rag_platform.release_draft"),
    )
    build_release = BuildRagReleaseUseCase(
        releases=releases,
        variants=variants,
        snapshots=snapshots,
        resolver=revision_resolver,
        memberships=memberships,
        ledger=build_ledger,
        bindings=bindings,
    )
    validate_release = ValidateRagReleaseUseCase(
        releases=releases,
        variants=variants,
        snapshots=snapshots,
        memberships=memberships,
        configuration_fingerprints=configuration_fingerprints,
        logger=get_logger("rag_platform.release_validate"),
    )
    publish_release = PublishRagReleaseUseCase(
        releases=releases,
        access_policy=access_policy,
        transactions=transactions,
        logger=get_logger("rag_platform.publication"),
    )
    rebuild_platform = _build_rag_platform_rebuild(
        connection=connection,
        indexing_runs=indexing_runs,
        bundles=bundles,
        profiles=profiles,
        index_bundle=index_bundle,
        run_documents=run_documents,
    )

    return RagPlatformServices(
        create_project=CreateProjectUseCase(
            projects=projects, storage_roots=storage_roots, access_policy=access_policy
        ),
        get_project=GetProjectUseCase(projects=projects),
        list_projects=ListProjectsUseCase(projects=projects),
        update_project_metadata=UpdateProjectMetadataUseCase(
            projects=projects, access_policy=access_policy
        ),
        get_project_configuration=GetProjectConfigurationUseCase(projects=projects),
        get_project_configuration_version=GetProjectConfigurationVersionUseCase(
            configurations=projects
        ),
        create_project_configuration_version=CreateProjectConfigurationVersionUseCase(
            projects=projects, configurations=projects, access_policy=access_policy
        ),
        list_processing_profiles=ListProcessingProfilesUseCase(
            processing_profiles=processing
        ),
        list_chunking_profiles=ListChunkingProfilesUseCase(chunking_profiles=chunking),
        get_variant_matrix=variant_matrix,
        create_variant_from_matrix_cell=CreateRagVariantFromMatrixCellUseCase(
            matrix=variant_matrix, create_variant=create_variant
        ),
        list_project_variants=ListProjectVariantsUseCase(variants=variants),
        create_corpus_snapshot=CreateCorpusSnapshotUseCase(
            snapshots=snapshots, documents=documents, access_policy=access_policy
        ),
        create_release_draft=release_draft,
        get_release=GetReleaseUseCase(releases=releases),
        list_project_releases=ListProjectReleasesUseCase(releases=releases),
        build_release=build_release,
        validate_release=validate_release,
        publish_release=publish_release,
        retire_release=RetireRagReleaseUseCase(
            releases=releases,
            access_policy=access_policy,
            logger=get_logger("rag_platform.release_retire"),
        ),
        rebuild_platform=rebuild_platform,
    )


def _build_rag_platform_draft(*, connection: object | None) -> object:
    """Cablea ``CreateRagReleaseDraftUseCase`` (postgres o in-memory).

    El ``release_id_factory`` acuña un ``ragr_`` único por DRAFT (uuid): el orden
    lo lleva ``release_number`` por variante, no el id, así que un id fresco por
    intento es correcto y evita colisiones entre procesos.
    """

    import uuid

    from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
    from rag_platform.domain.identity import IdentityKind, PlatformId

    def _release_id_factory() -> PlatformId:
        return PlatformId(
            kind=IdentityKind.RAG_RELEASE, value="ragr_" + uuid.uuid4().hex[:16]
        )

    if connection is None:
        from rag_platform.infrastructure.in_memory.release_repositories import (
            InMemoryCorpusSnapshotReader,
            InMemoryCurrentConfigurationVersionReader,
            InMemoryRagReleaseRepository,
            InMemoryRagVariantReader,
        )
        from rag_platform.infrastructure.in_memory.repositories import (
            InMemoryTargetBindingResolver,
        )

        return CreateRagReleaseDraftUseCase(
            variants=InMemoryRagVariantReader(()),
            snapshots=InMemoryCorpusSnapshotReader(()),
            bindings=InMemoryTargetBindingResolver(()),
            releases=InMemoryRagReleaseRepository(),
            configuration_versions=InMemoryCurrentConfigurationVersionReader(),
            release_id_factory=_release_id_factory,
            logger=get_logger("rag_platform.release_draft"),
        )

    from rag_platform.infrastructure.postgres.document_repositories import (
        PostgresCorpusSnapshotRepository,
    )
    from rag_platform.infrastructure.postgres.project_repositories import (
        PostgresProjectRepository,
        PostgresRagVariantRepository,
        PostgresTargetBindingResolver,
    )
    from rag_platform.infrastructure.postgres.release_repositories import (
        PostgresRagReleaseRepository,
    )

    return CreateRagReleaseDraftUseCase(
        variants=PostgresRagVariantRepository(connection),
        snapshots=PostgresCorpusSnapshotRepository(connection),
        bindings=PostgresTargetBindingResolver(connection),
        releases=PostgresRagReleaseRepository(connection),
        # ``PostgresProjectRepository`` satisface el reader de versión vigente.
        configuration_versions=PostgresProjectRepository(connection),
        release_id_factory=_release_id_factory,
        logger=get_logger("rag_platform.release_draft"),
    )


def _build_rag_platform_validate(*, connection: object | None) -> object:
    """Cablea ``ValidateRagReleaseUseCase`` (postgres o in-memory)."""

    from rag_platform.application.release_validator import ValidateRagReleaseUseCase

    if connection is None:
        from rag_platform.infrastructure.in_memory.release_repositories import (
            InMemoryCorpusSnapshotReader,
            InMemoryRagReleaseMembershipRepository,
            InMemoryRagReleaseRepository,
            InMemoryRagVariantReader,
            StaticConfigurationFingerprintReader,
        )

        return ValidateRagReleaseUseCase(
            releases=InMemoryRagReleaseRepository(),
            variants=InMemoryRagVariantReader(()),
            snapshots=InMemoryCorpusSnapshotReader(()),
            memberships=InMemoryRagReleaseMembershipRepository(),
            configuration_fingerprints=StaticConfigurationFingerprintReader(),
            logger=get_logger("rag_platform.release_validate"),
        )

    from rag_platform.infrastructure.postgres.document_repositories import (
        PostgresCorpusSnapshotRepository,
    )
    from rag_platform.infrastructure.postgres.project_repositories import (
        PostgresProjectConfigurationFingerprintReader,
        PostgresRagVariantRepository,
    )
    from rag_platform.infrastructure.postgres.release_repositories import (
        PostgresRagReleaseMembershipRepository,
        PostgresRagReleaseRepository,
    )

    return ValidateRagReleaseUseCase(
        releases=PostgresRagReleaseRepository(connection),
        variants=PostgresRagVariantRepository(connection),
        snapshots=PostgresCorpusSnapshotRepository(connection),
        memberships=PostgresRagReleaseMembershipRepository(connection),
        configuration_fingerprints=PostgresProjectConfigurationFingerprintReader(
            connection
        ),
        logger=get_logger("rag_platform.release_validate"),
    )


def _build_rag_platform_rebuild(
    *,
    connection: object | None,
    indexing_runs: object,
    bundles: object,
    profiles: object,
    index_bundle: object,
    run_documents: object,
) -> object | None:
    """Cablea el rebuild pure-platform (Fase 4 Stage 3) en el composition root.

    Encadena indexado bundle-first + materialización sellada reusando los casos de
    uso ya construidos. La materialización sella en Postgres, así que sin conexión
    (modo memoria) no aplica y se deja ``None``.
    """

    if connection is None:
        return None

    from indexing.application.bundle_first.index_bundle import (
        CreateIndexingRunUseCase,
        IndexingRunExecutor,
    )
    from rag_platform.application.rebuild_orchestrator import (
        RebuildPlatformArtifactsUseCase,
    )
    from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
    from rag_platform.infrastructure.postgres.vector_repositories import (
        PostgresIndexingMaterializationRepository,
    )

    return RebuildPlatformArtifactsUseCase(
        # ponytail: se reconstruyen create_run/executor (thin wrappers sobre los
        # mismos repos); el rebuild usa execute() síncrono, no el pool de submit().
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
        run_documents=run_documents,
        # El orquestador deriva checksum/propietario/dimensión/métrica del bundle y
        # del perfil (target-side), así que ambos repos se inyectan aquí.
        bundles=bundles,
        profiles=profiles,
        materialize=MaterializeVectorsUseCase(
            repository=PostgresIndexingMaterializationRepository(connection)
        ),
        # ponytail: default del target (indexing_targets.storage_schema_version); si
        # coexisten targets con schema versions distintas, leerlo del target resuelto.
        storage_schema_version="idx-vec-v1",
    )


def _platform_data_root(chunks_root: Path) -> Path:
    """Return the ``.../data`` root that contains ``projects/``.

    El almacenamiento de plataforma vive en ``<data>/projects/<slug>/<root>`` y
    ``ProjectStorageResolver`` re-deriva ``projects/<slug>`` a partir de ``<data>``.
    Derivarlo como ``chunks_root.parent`` doblaba ``projects/<slug>`` cuando la raíz
    de chunks ya era la del proyecto; se ancla en ``projects/`` para evitarlo.
    """

    for parent in chunks_root.parents:
        if parent.name == "projects":
            return parent.parent
    return chunks_root.parent


def _build_rag_platform_build(*, connection: object | None, data_root: Path) -> object:
    """Build the release planner with either in-memory or Postgres-backed adapters."""

    from rag_platform.application.release_build_service import BuildRagReleaseUseCase
    from rag_platform.infrastructure.in_memory.release_build_resolver import (
        InMemoryRevisionArtifactResolver,
    )

    """ a futuro eliminacion del in memory y reemplazo por postgres, pero por ahora se mantiene para pruebas y demos locales """
    from rag_platform.infrastructure.in_memory.release_repositories import (
        InMemoryCorpusSnapshotReader,
        InMemoryRagReleaseMembershipRepository,
        InMemoryRagReleaseRepository,
        InMemoryRagVariantReader,
    )
    from rag_platform.infrastructure.in_memory.repositories import (
        InMemoryRagBuildRunRepository,
        InMemoryTargetBindingResolver,
    )

    if connection is None:
        return BuildRagReleaseUseCase(
            releases=InMemoryRagReleaseRepository(),
            variants=InMemoryRagVariantReader(()),
            snapshots=InMemoryCorpusSnapshotReader(()),
            resolver=InMemoryRevisionArtifactResolver(),
            memberships=InMemoryRagReleaseMembershipRepository(),
            ledger=InMemoryRagBuildRunRepository(),
            bindings=InMemoryTargetBindingResolver(()),
        )

    from rag_platform.infrastructure.postgres.document_repositories import (
        PostgresCorpusSnapshotRepository,
    )
    from rag_platform.infrastructure.postgres.project_repositories import (
        PostgresRagVariantRepository,
        PostgresTargetBindingResolver,
    )
    from rag_platform.infrastructure.postgres.release_repositories import (
        PostgresRagReleaseMembershipRepository,
        PostgresRagReleaseRepository,
    )
    from rag_platform.infrastructure.release_build_resolver import (
        PostgresRevisionArtifactResolver,
    )
    from rag_platform.infrastructure.postgres.artifact_repositories import (
        PostgresRagBuildRunRepository,
    )

    return BuildRagReleaseUseCase(
        releases=PostgresRagReleaseRepository(connection),
        variants=PostgresRagVariantRepository(connection),
        snapshots=PostgresCorpusSnapshotRepository(connection),
        resolver=PostgresRevisionArtifactResolver(
            connection=connection,
            data_root=data_root,
        ),
        memberships=PostgresRagReleaseMembershipRepository(connection),
        ledger=PostgresRagBuildRunRepository(connection),
        bindings=PostgresTargetBindingResolver(connection),
    )


def _build_rag_platform_publish(*, connection: object | None, transactions: object) -> object:
    """Build the release publication use case (postgres or in-memory repo).

    Kept out of the main wiring so the legacy surface is unchanged when the flag
    is off. The access policy authorises any non-empty operator; a project-scoped
    policy is layered by the API dependency (Fase 7).
    """

    from rag_platform.application.publication_service import PublishRagReleaseUseCase
    from rag_platform.infrastructure.in_memory.repositories import AllowAllAccessPolicy

    if connection is None:
        from rag_platform.infrastructure.in_memory.release_repositories import (
            InMemoryRagReleaseRepository,
        )

        releases: object = InMemoryRagReleaseRepository()
    else:
        from rag_platform.infrastructure.postgres.release_repositories import (
            PostgresRagReleaseRepository,
        )

        releases = PostgresRagReleaseRepository(connection)
    return PublishRagReleaseUseCase(
        releases=releases,
        access_policy=AllowAllAccessPolicy(),
        transactions=transactions,
        logger=get_logger("rag_platform.publication"),
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
    _emit_startup_observability(services, connection=connection)
    return services


def _emit_startup_observability(
    services: PipelineServices, *, connection: object | None = None
) -> None:
    """Emit a safe, structured startup event describing the composition."""

    overview: dict[str, object] = {}
    try:
        overview = services.indexing_read_service.overview()
    except Exception as error:  # noqa: BLE001 - observability must never block startup
        # Un read fallido aborta la transacción de la conexión compartida (psycopg2
        # sin autocommit). Sin rollback, el resto del arranque (reconcile, etc.)
        # hereda esa transacción abortada y muere con InFailedSqlTransaction. La
        # garantía "observability must never block startup" exige limpiar la conexión.
        if connection is not None:
            try:
                connection.rollback()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - rollback best-effort en el borde de arranque
                pass
        logger.warning(
            "startup_overview_unavailable",
            extra={"stage": "backend", "error_type": type(error).__name__},
        )

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
