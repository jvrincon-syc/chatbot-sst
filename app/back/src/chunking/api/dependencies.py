from __future__ import annotations

from pathlib import Path

from fastapi import Request

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.application.run_service import ChunkingRunService
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource


def build_run_service(
    *,
    docs_normalized: Path,
    chunks_root: Path,
) -> ChunkingRunService:
    chunk_repository = FilesystemChunkBundleRepository(output_root=chunks_root)
    return ChunkingRunService(
        docs_normalized=docs_normalized,
        chunks_root=chunks_root,
        source=Schema2NormalizedDocumentSource(docs_normalized=docs_normalized),
        orchestrator=ChunkingOrchestrator(
            engine=LocalChunkingEngine(),
            bundle_repository=chunk_repository,
            run_repository=FilesystemRunRepository(output_root=chunks_root),
        ),
        chunk_repository=chunk_repository,
    )


def get_run_service(request: Request) -> ChunkingRunService:
    return request.app.state.chunking_run_service
