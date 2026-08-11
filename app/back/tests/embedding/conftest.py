from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from embedding.application.bundle_builder import (
    EmbeddingBundleBuilder,
    EmbeddingIndexingReadinessEvaluator,
    EmbeddingBundleValidator,
)
from embedding.application.engine_registry import DefaultEmbeddingEngineRegistry
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
from indexing.domain.bundle_first import IndexingTarget


from pipeline_fixtures import (
    ARTIFACT_RELPATH,
    CORPUS_VERSION,
    DIMENSION,
    DOCUMENT_ID,
    MOCK_REVISION,
    SOURCE_HASH,
    build_profile,
    build_target,
    write_chunk_bundle,
)


@dataclass
class EmbeddingHarness:
    """Fully wired in-memory embedding stack for tests."""

    profile: EmbeddingProfile
    chunk_bundle: ChunkBundleRef
    profiles: InMemoryEmbeddingProfileRepository
    chunk_bundles: InMemoryChunkBundleRepository
    runs: InMemoryEmbeddingRunRepository
    bundles: InMemoryEmbeddingBundleRepository
    readiness_checks: InMemoryReadinessCheckRepository
    targets: InMemoryIndexingTargetRepository
    registry: DefaultEmbeddingEngineRegistry
    artifacts: FilesystemEmbeddingBundleArtifactStore
    content_reader: FilesystemChunkBundleContentReader
    builder: EmbeddingBundleBuilder
    create_run: CreateEmbeddingRunUseCase
    executor: EmbeddingRunExecutor


@pytest.fixture
def harness(tmp_path: Path) -> EmbeddingHarness:
    profile = build_profile()
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    profiles = InMemoryEmbeddingProfileRepository([profile])
    chunk_bundles = InMemoryChunkBundleRepository([chunk_bundle])
    runs = InMemoryEmbeddingRunRepository()
    bundles = InMemoryEmbeddingBundleRepository()
    readiness_checks = InMemoryReadinessCheckRepository()
    targets = InMemoryIndexingTargetRepository([build_target()])
    registry = DefaultEmbeddingEngineRegistry(environ={}, allow_mock=True)
    artifacts = FilesystemEmbeddingBundleArtifactStore(root=tmp_path / "embeddings")
    content_reader = FilesystemChunkBundleContentReader(chunks_root=tmp_path / "chunks")
    builder = EmbeddingBundleBuilder(
        bundles=bundles,
        artifacts=artifacts,
        validator=EmbeddingBundleValidator(artifacts=artifacts),
        readiness_checks=readiness_checks,
        readiness_evaluator=EmbeddingIndexingReadinessEvaluator(targets=targets),
        batch_size=2,
    )
    return EmbeddingHarness(
        profile=profile,
        chunk_bundle=chunk_bundle,
        profiles=profiles,
        chunk_bundles=chunk_bundles,
        runs=runs,
        bundles=bundles,
        readiness_checks=readiness_checks,
        targets=targets,
        registry=registry,
        artifacts=artifacts,
        content_reader=content_reader,
        builder=builder,
        create_run=CreateEmbeddingRunUseCase(
            runs=runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            registry=registry,
        ),
        executor=EmbeddingRunExecutor(
            runs=runs,
            profiles=profiles,
            chunk_bundles=chunk_bundles,
            bundles=bundles,
            registry=registry,
            builder=builder,
            content_reader=content_reader,
        ),
    )
