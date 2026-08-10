from __future__ import annotations

from pathlib import Path

from fastapi import Request

from api.dependencies import _open_postgres_connection, _resolve_persistence_mode
from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.application.run_service import ChunkingRunService
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.postgres_chunk_repository import (
    FilesystemBackedPostgresChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from embedding.infrastructure.postgres.repositories import PostgresChunkBundleRepository

import os


def build_run_service(
    *,
    docs_normalized: Path,
    chunks_root: Path,
    connection: object | None = None,
    close_connection_on_close: bool = False,
) -> ChunkingRunService:
    chunk_repository: FilesystemChunkBundleRepository
    if connection is None:
        chunk_repository = FilesystemChunkBundleRepository(output_root=chunks_root)
    else:
        chunk_repository = FilesystemBackedPostgresChunkBundleRepository(
            output_root=chunks_root,
            ledger=PostgresChunkBundleRepository(connection),
            connection=connection,
            close_connection_on_close=close_connection_on_close,
        )
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


def build_run_service_from_env(
    *,
    docs_normalized: Path,
    chunks_root: Path,
) -> ChunkingRunService:
    connection: object | None = None
    close_connection_on_close = False
    if _resolve_persistence_mode(os.environ) == "postgres":
        dsn = (os.environ.get("SST_POSTGRES_DSN") or "").strip()
        if dsn:
            connection = _open_postgres_connection(dsn)
            close_connection_on_close = True
    return build_run_service(
        docs_normalized=docs_normalized,
        chunks_root=chunks_root,
        connection=connection,
        close_connection_on_close=close_connection_on_close,
    )


def get_run_service(request: Request) -> ChunkingRunService:
    return request.app.state.chunking_run_service
