"""Production resolver for release builds backed by Postgres and project storage.

This adapter wires the existing chunking, embedding and indexing services into the
platform release planner without re-implementing those algorithms. It assumes the
normalized Schema 2 artifacts already exist under the project's isolated storage
root and fails closed when one required artifact or profile is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile as RuntimeChunkingProfile
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.postgres_chunk_repository import (
    FilesystemBackedPostgresChunkBundleRepository,
)
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from core.logging.logger import get_logger
from embedding.application.bundle_builder import (
    EmbeddingBundleBuilder,
    EmbeddingBundleValidator,
    EmbeddingIndexingReadinessEvaluator,
)
from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
from embedding.application.run_service import (
    CreateEmbeddingRunRequest,
    CreateEmbeddingRunUseCase,
    EmbeddingRunExecutor,
)
from embedding.domain.errors import ChunkBundleNotFound
from embedding.domain.models import EmbeddingBundle, EmbeddingProfile, canonical_json
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from embedding.infrastructure.filesystem.chunk_bundle_catalog import (
    FilesystemChunkBundleCatalogRepository,
    HybridChunkBundleRepository,
)
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    FilesystemChunkBundleContentReader,
)
from embedding.infrastructure.postgres.repositories import (
    PostgresChunkBundleRepository,
    PostgresEmbeddingBundleRepository,
    PostgresEmbeddingProfileRepository,
    PostgresEmbeddingRunRepository,
    PostgresIndexingTargetRepository,
    PostgresReadinessCheckRepository,
)
from indexing.application.bundle_first.index_bundle import (
    CreateIndexingRunRequest,
    CreateIndexingRunUseCase,
    IndexEmbeddingBundleUseCase,
    IndexingRunExecutor,
)
from indexing.infrastructure.postgres.bundle_first import (
    PostgresIndexingNodeWriter,
    PostgresIndexingRunDocumentRepository,
    PostgresIndexingRunRepository,
    PsycopgTransactionManager,
)
from indexing.infrastructure.postgres.vector_repository import PostgresVectorRepository
from rag_platform.application.artifact_reuse_service import ArtifactReusePolicy
from rag_platform.application.context import NormalizedArtifactBuilder, SourceDocumentRepository
from rag_platform.application.rebuild_orchestrator import (
    PlatformBuildContext,
    RebuildPlatformArtifactsUseCase,
)
from rag_platform.application.release_build_service import (
    RevisionArtifacts,
    StageResolution,
)
from rag_platform.application.vector_materialization import MaterializeVectorsUseCase
from rag_platform.domain.identity import (
    ProjectDocumentContext,
    normalized_document_id,
)
from rag_platform.domain.models import BuildOutcome, ReuseKind
from rag_platform.infrastructure.postgres.artifact_repositories import (
    PostgresSealedChunkBundleRepository,
    PostgresRagBuildRunRepository,
)
from rag_platform.infrastructure.postgres.document_repositories import (
    PostgresNormalizedArtifactRepository,
    PostgresSourceDocumentRepository,
)
from rag_platform.infrastructure.postgres.project_repositories import (
    PostgresChunkingProfileRepository,
    PostgresProcessingProfileRepository,
    PostgresRagVariantRepository,
)
from rag_platform.infrastructure.postgres.vector_repositories import (
    PostgresIndexingMaterializationRepository,
    PostgresSealedEmbeddingBundleRepository,
)
from rag_platform.infrastructure.runtime_chunking_profiles import (
    RuntimeChunkingProfileResolver,
)
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver


@dataclass(frozen=True)
class _ProjectRuntime:
    profiles: PostgresEmbeddingProfileRepository
    targets: PostgresIndexingTargetRepository
    chunk_bundles: HybridChunkBundleRepository
    bundles: PostgresEmbeddingBundleRepository
    create_embedding_run: CreateEmbeddingRunUseCase
    embedding_executor: EmbeddingRunExecutor
    create_indexing_run: CreateIndexingRunUseCase
    indexing_executor: IndexingRunExecutor
    run_documents: PostgresIndexingRunDocumentRepository


class Schema2FilesystemNormalizedArtifactBuilder:
    """Resolve one existing Schema 2 normalized artifact under the project root."""

    def __init__(
        self,
        *,
        source_documents: SourceDocumentRepository,
        storage: ProjectStorageResolver,
        processing_profile_fingerprint: str,
        schema_version: str = "2.0",
    ) -> None:
        self._source_documents = source_documents
        self._storage = storage
        self._processing_profile_fingerprint = processing_profile_fingerprint
        self._schema_version = schema_version

    def build(self, context: ProjectDocumentContext):
        revision = self._source_documents.get_revision(context.source_document_revision_id)
        artifact_relpath = (
            f"normalized/{Path(revision.source_relpath).with_suffix('.md').as_posix()}"
        )
        normalized_root = self._storage.resolve_root(context.project_id, "normalized")
        absolute_path = self._storage.resolve_artifact(
            context.project_id, PurePosixPath(artifact_relpath)
        )
        relative_markdown = absolute_path.relative_to(normalized_root).as_posix()
        Schema2NormalizedDocumentSource(docs_normalized=normalized_root).load(relative_markdown)
        from rag_platform.domain.models import NormalizedDocumentArtifact

        return NormalizedDocumentArtifact(
            project_id=context.project_id,
            source_document_revision_id=context.source_document_revision_id,
            processing_profile_fingerprint=self._processing_profile_fingerprint,
            schema_version=self._schema_version,
            artifact_relpath=artifact_relpath,
        )


class PostgresRevisionArtifactResolver:
    """Resolve release artifacts using Postgres ledgers and project storage."""

    def __init__(
        self,
        *,
        connection: object,
        data_root: Path,
        allow_mock_embedding: bool = False,
        chunk_bundle_schema_version: str = "sealed-v1",
        source_documents: PostgresSourceDocumentRepository | None = None,
        normalized_artifacts: PostgresNormalizedArtifactRepository | None = None,
        variants: PostgresRagVariantRepository | None = None,
        processing_profiles: PostgresProcessingProfileRepository | None = None,
        chunking_profiles: PostgresChunkingProfileRepository | None = None,
        sealed_chunk_bundles: PostgresSealedChunkBundleRepository | None = None,
        sealed_embedding_bundles: PostgresSealedEmbeddingBundleRepository | None = None,
        materializations: PostgresIndexingMaterializationRepository | None = None,
    ) -> None:
        self._connection = connection
        self._storage = ProjectStorageResolver(data_root)
        self._source_documents = source_documents or PostgresSourceDocumentRepository(
            connection
        )
        self._normalized_artifacts = normalized_artifacts or PostgresNormalizedArtifactRepository(
            connection
        )
        self._variants = variants or PostgresRagVariantRepository(connection)
        self._processing_profiles = processing_profiles or PostgresProcessingProfileRepository(
            connection
        )
        self._chunking_profiles = chunking_profiles or PostgresChunkingProfileRepository(
            connection
        )
        self._sealed_chunk_bundles = sealed_chunk_bundles or PostgresSealedChunkBundleRepository(
            connection
        )
        self._sealed_embedding_bundles = (
            sealed_embedding_bundles or PostgresSealedEmbeddingBundleRepository(connection)
        )
        self._materializations = materializations or PostgresIndexingMaterializationRepository(
            connection
        )
        self._chunk_bundle_schema_version = chunk_bundle_schema_version
        self._allow_mock_embedding = allow_mock_embedding
        self._runtime_cache: dict[str, _ProjectRuntime] = {}

    def resolve(self, *, context, source_document_revision_id):
        variant = self._variants.get(context.rag_variant_id)
        processing_profile = self._processing_profiles.get(variant.processing_profile_id)
        chunking_profile = self._chunking_profiles.get(variant.chunking_profile_id)
        runtime = self._runtime_for(context.project_id)
        embedding_profile = runtime.profiles.get(context.embedding_profile_id)
        reuse = ArtifactReusePolicy(
            normalized_repository=self._normalized_artifacts,
            chunk_bundle_repository=self._sealed_chunk_bundles,
            embedding_bundle_repository=self._sealed_embedding_bundles,
        )

        normalized_artifact, normalize_resolution = self._resolve_normalized(
            context=context,
            source_document_revision_id=source_document_revision_id,
            processing_profile_id=variant.processing_profile_id,
            processing_profile_fingerprint=processing_profile.fingerprint,
        )
        normalized_id = normalized_document_id(
            project_id=context.project_id.value,
            source_document_revision_id=source_document_revision_id.value,
            processing_profile_fingerprint=processing_profile.fingerprint,
        )
        chunk_bundle, chunk_resolution = self._resolve_chunk_bundle(
            context=context,
            normalized_artifact=normalized_artifact,
            normalized_document_id=normalized_id,
            chunking_profile_fingerprint=chunking_profile.fingerprint,
            reuse=reuse,
        )
        embedding_bundle, embed_resolution = self._resolve_embedding_bundle(
            context=context,
            runtime=runtime,
            reuse=reuse,
            embedding_profile=embedding_profile,
            chunk_bundle_id=chunk_bundle.chunk_bundle_id,
        )
        index_resolution = self._resolve_materialization(
            context=context,
            runtime=runtime,
            embedding_profile=embedding_profile,
            embedding_bundle=embedding_bundle,
        )
        return RevisionArtifacts(
            normalize=normalize_resolution,
            chunk=chunk_resolution,
            embed=embed_resolution,
            index=index_resolution,
        )

    def build_ledger(self) -> PostgresRagBuildRunRepository:
        return PostgresRagBuildRunRepository(self._connection)

    def _resolve_normalized(
        self,
        *,
        context,
        source_document_revision_id,
        processing_profile_id,
        processing_profile_fingerprint: str,
    ):
        existing = self._normalized_artifacts.find(
            project_id=context.project_id,
            source_document_revision_id=source_document_revision_id,
            processing_profile_fingerprint=processing_profile_fingerprint,
        )
        if existing is not None and self._normalized_exists(
            context.project_id, existing.artifact_relpath
        ):
            normalized_id_value = normalized_document_id(
                project_id=context.project_id.value,
                source_document_revision_id=source_document_revision_id.value,
                processing_profile_fingerprint=processing_profile_fingerprint,
            )
            return existing, StageResolution(
                artifact_id=normalized_id_value,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            )

        builder = Schema2FilesystemNormalizedArtifactBuilder(
            source_documents=self._source_documents,
            storage=self._storage,
            processing_profile_fingerprint=processing_profile_fingerprint,
        )
        built = self._normalized_artifacts.add(
            builder.build(
                ProjectDocumentContext(
                    project_id=context.project_id,
                    source_document_id=self._source_documents.get_revision(
                        source_document_revision_id
                    ).logical_document_id,
                    source_document_revision_id=source_document_revision_id,
                    processing_profile_id=processing_profile_id,
                )
            )
        )
        _commit_if_possible(self._connection)
        normalized_id_value = normalized_document_id(
            project_id=context.project_id.value,
            source_document_revision_id=source_document_revision_id.value,
            processing_profile_fingerprint=processing_profile_fingerprint,
        )
        return built, StageResolution(
            artifact_id=normalized_id_value,
            outcome=BuildOutcome.BUILT,
        )

    def _resolve_chunk_bundle(
        self,
        *,
        context,
        normalized_artifact,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        reuse: ArtifactReusePolicy,
    ):
        reusable = reuse.find_reusable_chunk_bundle(
            project_id=context.project_id,
            normalized_document_id=normalized_document_id,
            chunking_profile_fingerprint=chunking_profile_fingerprint,
            bundle_schema_version=self._chunk_bundle_schema_version,
        )
        if reusable is not None:
            return reusable, StageResolution(
                artifact_id=reusable.chunk_bundle_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            )

        runtime_profile = self._runtime_chunking_profile(context.rag_variant_id)
        normalized_root = self._storage.resolve_root(context.project_id, "normalized")
        chunks_root = self._storage.resolve_root(context.project_id, "chunks")
        source = Schema2NormalizedDocumentSource(docs_normalized=normalized_root)
        chunk_repository = FilesystemBackedPostgresChunkBundleRepository(
            output_root=chunks_root,
            ledger=PostgresChunkBundleRepository(self._connection),
            connection=self._connection,
            project_id=context.project_id.value,
        )
        orchestrator = ChunkingOrchestrator(
            engine=LocalChunkingEngine(),
            bundle_repository=chunk_repository,
            run_repository=FilesystemRunRepository(output_root=chunks_root),
        )
        document = source.load(
            _relative_under_root(normalized_artifact.artifact_relpath, "normalized")
        )
        orchestrator.process_document(document=document, profile=runtime_profile)
        metadata = chunk_repository.read_metadata(document=document)
        if metadata is None:
            raise ChunkBundleNotFound("chunk bundle metadata was not persisted")
        bundle = PostgresChunkBundleRepository(self._connection).get(
            metadata.bundle_fingerprint
        )
        self._sealed_chunk_bundles.register_sealed_bundle(
            bundle,
            project_id=context.project_id,
            normalized_document_id=normalized_document_id,
            chunking_profile_fingerprint=chunking_profile_fingerprint,
            bundle_schema_version=self._chunk_bundle_schema_version,
        )
        _commit_if_possible(self._connection)
        stored = PostgresChunkBundleRepository(self._connection).get(bundle.chunk_bundle_id)
        return stored, StageResolution(
            artifact_id=stored.chunk_bundle_id,
            outcome=BuildOutcome.BUILT,
        )

    def _resolve_embedding_bundle(
        self,
        *,
        context,
        runtime: _ProjectRuntime,
        reuse: ArtifactReusePolicy,
        embedding_profile: EmbeddingProfile,
        chunk_bundle_id: str,
    ):
        reusable = reuse.find_reusable_embedding_bundle(
            project_id=context.project_id,
            source_chunk_bundle_id=chunk_bundle_id,
            embedding_profile_id=embedding_profile.profile_id,
            configuration_fingerprint=embedding_profile.expected_fingerprint().value,
            expected_dimension=embedding_profile.dimension,
            expected_metric=embedding_profile.distance_metric,
        )
        if reusable is not None:
            bundle = runtime.bundles.get(reusable.embedding_bundle_id)
            return bundle, StageResolution(
                artifact_id=bundle.embedding_bundle_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            )

        run = runtime.create_embedding_run.execute(
            request=CreateEmbeddingRunRequest(
                chunk_bundle_id=chunk_bundle_id,
                profile_id=embedding_profile.profile_id,
                project_id=context.project_id.value,
                rag_variant_id=context.rag_variant_id.value,
                rag_release_id=context.rag_release_id.value,
            ),
            idempotency_key=_idempotency_key(
                "embed",
                context.rag_release_id.value,
                chunk_bundle_id,
                embedding_profile.profile_id,
            ),
        )
        completed = runtime.embedding_executor.execute(run.embedding_run_id)
        if completed.status != "completed" or completed.produced_embedding_bundle_id is None:
            raise RuntimeError(
                f"embedding run {completed.embedding_run_id} did not complete successfully"
            )
        bundle = runtime.bundles.get(str(completed.produced_embedding_bundle_id))
        return bundle, StageResolution(
            artifact_id=bundle.embedding_bundle_id,
            outcome=BuildOutcome.BUILT,
        )

    def _resolve_materialization(
        self,
        *,
        context,
        runtime: _ProjectRuntime,
        embedding_profile: EmbeddingProfile,
        embedding_bundle: EmbeddingBundle,
    ):
        target = runtime.targets.get(context.indexing_target_id)
        existing = self._materializations.find_sealed(
            project_id=context.project_id,
            embedding_bundle_id=embedding_bundle.embedding_bundle_id,
            indexing_target_id=context.indexing_target_id,
            storage_schema_version=target.storage_schema_version,
        )
        if existing is not None:
            return StageResolution(
                artifact_id=existing.materialization_id,
                outcome=BuildOutcome.REUSED,
                reuse_kind=ReuseKind.EXACT_IDENTITY,
            )

        # RebuildPlatformArtifactsUseCase deriva checksum/dimensión/métrica/conteos
        # server-side desde el bundle y el perfil del target; el resolver solo aporta
        # contexto validado + embedding_bundle_id (firma vigente de rebuild_orchestrator).
        rebuild = RebuildPlatformArtifactsUseCase(
            create_indexing_run=runtime.create_indexing_run,
            indexing_executor=runtime.indexing_executor,
            run_documents=runtime.run_documents,
            bundles=runtime.bundles,
            profiles=runtime.profiles,
            materialize=MaterializeVectorsUseCase(repository=self._materializations),
            storage_schema_version=target.storage_schema_version,
        )
        result = rebuild.execute(
            context=PlatformBuildContext(
                project_id=context.project_id,
                rag_variant_id=context.rag_variant_id,
                rag_release_id=context.rag_release_id,
            ),
            embedding_bundle_id=embedding_bundle.embedding_bundle_id,
            idempotency_key=_idempotency_key(
                "index",
                context.rag_release_id.value,
                embedding_bundle.embedding_bundle_id,
                context.indexing_target_id,
            ),
        )
        _commit_if_possible(self._connection)
        return StageResolution(
            artifact_id=result.materialization.materialization_id,
            outcome=BuildOutcome.BUILT,
        )

    def _runtime_for(self, project_id) -> _ProjectRuntime:
        cached = self._runtime_cache.get(project_id.value)
        if cached is not None:
            return cached
        chunks_root = self._storage.resolve_root(project_id, "chunks")
        embeddings_root = self._storage.resolve_root(project_id, "embeddings")
        profiles = PostgresEmbeddingProfileRepository(self._connection)
        targets = PostgresIndexingTargetRepository(self._connection)
        chunk_bundles = HybridChunkBundleRepository(
            primary=PostgresChunkBundleRepository(self._connection),
            filesystem=FilesystemChunkBundleCatalogRepository(chunks_root=chunks_root),
        )
        bundles = PostgresEmbeddingBundleRepository(self._connection)
        readiness_checks = PostgresReadinessCheckRepository(self._connection)
        registry = DefaultEmbeddingEngineRegistry(allow_mock=self._allow_mock_embedding)
        artifacts = FilesystemEmbeddingBundleArtifactStore(root=embeddings_root)
        content_reader = FilesystemChunkBundleContentReader(chunks_root=chunks_root)
        builder = EmbeddingBundleBuilder(
            bundles=bundles,
            artifacts=artifacts,
            validator=EmbeddingBundleValidator(artifacts=artifacts),
            readiness_checks=readiness_checks,
            readiness_evaluator=EmbeddingIndexingReadinessEvaluator(targets=targets),
        )
        run_documents = PostgresIndexingRunDocumentRepository(self._connection)
        index_bundle = IndexEmbeddingBundleUseCase(
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            targets=targets,
            nodes=PostgresIndexingNodeWriter(self._connection),
            vectors=PostgresVectorRepository(self._connection),
            artifacts=artifacts,
            content_reader=content_reader,
            run_documents=run_documents,
            readiness_checks=readiness_checks,
            transactions=PsycopgTransactionManager(self._connection),
        )
        runtime = _ProjectRuntime(
            profiles=profiles,
            targets=targets,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            create_embedding_run=CreateEmbeddingRunUseCase(
                runs=PostgresEmbeddingRunRepository(self._connection),
                profiles=profiles,
                chunk_bundles=chunk_bundles,
                registry=registry,
                connection=self._connection,
            ),
            embedding_executor=EmbeddingRunExecutor(
                runs=PostgresEmbeddingRunRepository(self._connection),
                profiles=profiles,
                chunk_bundles=chunk_bundles,
                bundles=bundles,
                registry=registry,
                builder=builder,
                content_reader=content_reader,
                connection=self._connection,
            ),
            create_indexing_run=CreateIndexingRunUseCase(
                runs=PostgresIndexingRunRepository(self._connection),
                bundles=bundles,
                profiles=profiles,
                index_use_case=index_bundle,
            ),
            indexing_executor=IndexingRunExecutor(
                runs=PostgresIndexingRunRepository(self._connection),
                index_use_case=index_bundle,
            ),
            run_documents=run_documents,
        )
        self._runtime_cache[project_id.value] = runtime
        return runtime

    def _runtime_chunking_profile(self, rag_variant_id) -> RuntimeChunkingProfile:
        variant = self._variants.get(rag_variant_id)
        platform_profile = self._chunking_profiles.get(variant.chunking_profile_id)
        # Mapea la receta persistida (v1/v2) a su runtime concreto; nunca colapsa
        # todo a v1. Una receta desconocida falla cerrado en el resolver.
        return RuntimeChunkingProfileResolver().resolve(platform_profile)

    def _normalized_exists(self, project_id, artifact_relpath: str | None) -> bool:
        if not artifact_relpath:
            return False
        candidate = self._storage.resolve_artifact(
            project_id, PurePosixPath(artifact_relpath)
        )
        return candidate.exists()


def _relative_under_root(artifact_relpath: str | None, root_name: str) -> str:
    if not artifact_relpath:
        raise ValueError(f"artifact_relpath is required under {root_name}")
    relpath = PurePosixPath(artifact_relpath)
    parts = relpath.parts
    if parts and parts[0] == root_name:
        return PurePosixPath(*parts[1:]).as_posix()
    return relpath.as_posix()


def _materialization_checksum(
    *,
    embedding_bundle: EmbeddingBundle,
    indexing_target_id: str,
    storage_schema_version: str,
) -> str:
    from hashlib import sha256

    payload = canonical_json(
        {
            "embedding_bundle_id": embedding_bundle.embedding_bundle_id,
            "indexing_target_id": indexing_target_id,
            "storage_schema_version": storage_schema_version,
            "source_chunk_bundle_id": embedding_bundle.source_chunk_bundle_id,
            "configuration_fingerprint": embedding_bundle.configuration_fingerprint,
            "source_content_fingerprint": embedding_bundle.source_content_fingerprint,
            "checksums": embedding_bundle.checksums,
            "vector_count": embedding_bundle.vector_count,
            "dimension": embedding_bundle.dimension,
            "distance_metric": embedding_bundle.distance_metric,
        }
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _idempotency_key(prefix: str, *parts: str) -> str:
    from hashlib import sha256

    payload = canonical_json([prefix, *parts])
    return f"{prefix}-{sha256(payload.encode('utf-8')).hexdigest()}"


def _commit_if_possible(connection: object) -> None:
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()
