from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ingestion.paths import ArtifactPaths, stable_document_id
from indexing.application.use_cases.index_document import IndexDocumentUseCase
from indexing.domain.models import IndexingProfile
from indexing.domain.models import IndexableDocument, NormalizedArtifactRefs
from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pipeline_factory import (
    BundleLoader,
    FilesystemBundleLoader,
    LlamaIndexingPort,
)
from indexing.infrastructure.postgres.settings import PostgresIndexingSettings


DEFAULT_PROFILE = IndexingProfile(
    profile_id="llama-first-local-v1",
    chunking_version="structure-aware-v1",
    embedding_provider="mock",
    embedding_model="deterministic",
    embedding_dimension=384,
    vector_store="memory",
    metadata_schema_version="2.0",
)


@dataclass(frozen=True)
class PostgresIndexingComponents:
    profile: ResolvedIndexingProfile
    indexer_kwargs: dict[str, object]
    connection: object


class PostgresConnection(Protocol):
    def commit(self) -> None:
        """Commit the active transaction."""

    def rollback(self) -> None:
        """Roll back the active transaction."""

    def close(self) -> None:
        """Close the connection."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Llama-first indexing.")
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--only-source", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.profile_id)
    parser.add_argument("--store", choices=["memory", "postgres"], default="memory")
    parser.add_argument(
        "--ingestion-origin",
        choices=["local", "llama_cloud"],
        default="local",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--persist-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_indexing(
        normalized_root=Path(args.docs_normalized),
        only_sources=args.only_source,
        force=args.force,
        profile_id=args.profile,
        dry_run=args.dry_run,
        store=args.store,
        ingestion_origin=args.ingestion_origin,
        persist_confirmed=args.persist_confirmed,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] != "blocked" else 2


def run_indexing(
    *,
    normalized_root: Path,
    only_sources: list[str],
    force: bool,
    profile_id: str,
    dry_run: bool,
    bundle_loader: BundleLoader | None = None,
    store: str = "memory",
    ingestion_origin: IngestionOrigin = "local",
    persist_confirmed: bool = False,
    environ: Mapping[str, str] | None = None,
) -> dict:
    settings = PostgresIndexingSettings.from_env(environ or os.environ)
    if store == "postgres" and not persist_confirmed:
        return {
            "status": "blocked",
            "reason": "postgres_not_confirmed",
            "profile": profile_id,
            "store": store,
        }
    if store == "postgres" and not settings.is_configured:
        return {
            "status": "blocked",
            "reason": "postgres_dsn_missing",
            "profile": profile_id,
            "store": store,
        }

    manifest_path = normalized_root / "_manifests" / "inventory.json"
    if not manifest_path.exists():
        return {
            "status": "blocked",
            "reason": "inventory_manifest_not_found",
            "path": str(manifest_path),
            "profile": profile_id,
            "store": store,
        }

    inventory = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = inventory.get("records", inventory if isinstance(inventory, list) else [])
    selected = set(only_sources)
    candidates = [
        record
        for record in records
        if not selected or record.get("source_relpath") in selected
    ]
    approved = [
        record
        for record in candidates
        if record.get("processing_status") == "processed"
    ]

    if dry_run:
        return {
            "status": "dry_run",
            "profile": profile_id,
            "store": store,
            "ingestion_origin": ingestion_origin,
            "candidate_documents": len(candidates),
            "approved_documents": len(approved),
            "force": force,
        }

    profile = DEFAULT_PROFILE.model_copy(update={"profile_id": profile_id})
    indexer_kwargs: dict[str, object] = {}
    connection: PostgresConnection | None = None
    if store == "postgres":
        postgres_indexing = _postgres_indexing_components(
            settings=settings,
            profile_id=profile_id,
        )
        profile = _indexing_profile_from_resolved(postgres_indexing.profile)
        indexer_kwargs = postgres_indexing.indexer_kwargs
        indexer_kwargs["storage_mode"] = "postgres"
        indexer_kwargs["ingestion_origin"] = ingestion_origin
        connection = postgres_indexing.connection
    documents = [_indexable_document(record, profile) for record in approved]
    indexer = LlamaIndexingPort(
        bundle_loader=bundle_loader or FilesystemBundleLoader(normalized_root=normalized_root),
        **indexer_kwargs,
    )
    succeeded = False
    try:
        results = asyncio.run(_index_documents(indexer=indexer, documents=documents))
        succeeded = True
    finally:
        if connection is not None:
            finalize_postgres_connection(connection, succeeded=succeeded)
    return {
        "status": "indexed",
        "profile": profile_id,
        "store": store,
        "ingestion_origin": ingestion_origin,
        "candidate_documents": len(candidates),
        "approved_documents": len(approved),
        "indexed_documents": len(results),
        "indexed_parent_nodes": sum(result.indexed_parent_nodes for result in results),
        "indexed_child_nodes": sum(result.indexed_child_nodes for result in results),
        "deleted_stale_nodes": sum(result.deleted_stale_nodes for result in results),
        "warnings": [
            warning
            for result in results
            for warning in result.warnings
        ],
        "force": force,
    }


def _postgres_indexing_components(
    *,
    settings: PostgresIndexingSettings,
    profile_id: str,
) -> PostgresIndexingComponents:
    import psycopg2

    from indexing.application.profile_orchestrator import EmbeddingProfileOrchestrator
    from indexing.infrastructure.postgres.node_repository import PostgresNodeRepository
    from indexing.infrastructure.postgres.normalized_document_repository import (
        PostgresNormalizedDocumentRepository,
    )
    from indexing.infrastructure.postgres.profile_registry import PostgresProfileRegistry
    from indexing.infrastructure.postgres.vector_repository import PostgresVectorRepository

    connection = psycopg2.connect(settings.dsn)
    registry = PostgresProfileRegistry(connection)
    profile = registry.get(profile_id)
    return PostgresIndexingComponents(
        profile=profile,
        indexer_kwargs={
            "normalized_document_repository": PostgresNormalizedDocumentRepository(
                connection
            ),
            "node_repository": PostgresNodeRepository(connection),
            "vector_repository": PostgresVectorRepository(connection),
            "profile_orchestrator": EmbeddingProfileOrchestrator(registry),
        },
        connection=connection,
    )


def finalize_postgres_connection(
    connection: PostgresConnection,
    *,
    succeeded: bool,
) -> None:
    """Finalize a PostgreSQL transaction and close the connection."""

    if succeeded:
        connection.commit()
    else:
        connection.rollback()
    connection.close()


def _indexing_profile_from_resolved(profile: ResolvedIndexingProfile) -> IndexingProfile:
    return IndexingProfile(
        profile_id=profile.profile_id,
        chunking_version=profile.chunking_version,
        embedding_provider=profile.embedding_provider,
        embedding_model=profile.embedding_model,
        embedding_dimension=profile.embedding_dimension,
        vector_store=profile.vector_table,
        metadata_schema_version=profile.metadata_schema_version,
    )


def _indexable_document(record: dict, profile: IndexingProfile) -> IndexableDocument:
    source_relpath = str(record["source_relpath"])
    paths = ArtifactPaths.for_source(source_relpath)
    return IndexableDocument(
        document_id=str(record.get("document_id") or stable_document_id(source_relpath)),
        source_relpath=source_relpath,
        source_hash=_source_hash(record),
        document_status="processed",
        artifacts=NormalizedArtifactRefs(
            markdown=paths.markdown,
            metadata=paths.metadata,
            pages=paths.pages,
            tables=paths.tables,
            forms=paths.forms,
        ),
        profile=profile,
    )


def _source_hash(record: dict) -> str:
    value = str(record.get("source_hash") or record.get("content_hash") or "")
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")
    return value


async def _index_documents(*, indexer: LlamaIndexingPort, documents: list[IndexableDocument]):
    use_case = IndexDocumentUseCase(indexer=indexer)
    results = []
    for document in documents:
        results.append(await use_case.index(document))
    return results


if __name__ == "__main__":
    raise SystemExit(main())
