from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from core.logging.logger import configure_structured_logging  # noqa: E402
from core.logging.observability import (  # noqa: E402
    EventContext,
    EventStatus,
    ObservabilityDomain,
    ObservabilityEvent,
    emit_observability_event,
    measure_duration_ms,
)
from ingestion.paths import ArtifactPaths, stable_document_id
from ingestion.gui.review_store import load_review_decisions
from indexing.application.eligibility import IndexingEligibilityService
from indexing.application.use_cases.index_document import IndexDocumentUseCase
from indexing.domain.models import IndexingProfile
from indexing.domain.models import IndexableDocument, NormalizedArtifactRefs
from indexing.domain.profiles import IngestionOrigin, ResolvedIndexingProfile
from indexing.infrastructure.embeddings.settings import EmbeddingSettings
from indexing.infrastructure.llama_index.pipeline_factory import (
    BundleLoader,
    FilesystemBundleLoader,
    LlamaIndexingPort,
)
from indexing.infrastructure.postgres.settings import PostgresIndexingSettings


logger = logging.getLogger(__name__)
LIVE_POSTGRES_EMBEDDING_PROVIDERS = {"bge", "voyage"}


DEFAULT_PROFILE = IndexingProfile(
    profile_id="local-bge-m3-v1",
    chunking_version="structure-aware-v1",
    embedding_provider="bge",
    embedding_model="BAAI/bge-m3",
    embedding_dimension=1024,
    vector_store="idx_vec_local_bge_m3_v1",
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


def _emit_indexing_event(
    *,
    event: str,
    status: EventStatus,
    message: str,
    document_id: str | None = None,
    profile_id: str | None = None,
    provider: str | None = None,
    capability: str | None = None,
    configuration_hash: str | None = None,
    metrics: dict[str, int | float] | None = None,
    attributes: dict[str, object] | None = None,
    exception: BaseException | None = None,
) -> None:
    emit_observability_event(
        logger=logger,
        event=ObservabilityEvent(
            event=event,
            domain=ObservabilityDomain.INDEXING,
            status=status,
            message=message,
            context=EventContext(
                document_id=document_id,
                profile_id=profile_id,
                provider=provider,
                capability=capability,
                configuration_hash=configuration_hash,
            ),
            metrics=metrics or {},
            attributes=attributes or {},
        ),
        exception=exception,
    )


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
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()
    logger.info(
        "indexing command started: profile=%s store=%s dry_run=%s ingestion_origin=%s",
        args.profile,
        args.store,
        args.dry_run,
        args.ingestion_origin,
    )
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
    logger.info(
        "indexing command finished: status=%s profile=%s store=%s",
        summary["status"],
        summary["profile"],
        summary["store"],
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
    env = environ or os.environ
    settings = PostgresIndexingSettings.from_env(env)
    logger.info(
        "indexing run started: profile=%s store=%s ingestion_origin=%s dry_run=%s force=%s",
        profile_id,
        store,
        ingestion_origin,
        dry_run,
        force,
    )
    if store == "postgres" and not persist_confirmed:
        summary = {
            "status": "blocked",
            "reason": "postgres_not_confirmed",
            "profile": profile_id,
            "store": store,
        }
        _emit_indexing_event(
            event="indexing_profile_rejected",
            status=EventStatus.BLOCKED,
            message="Indexing blocked: PostgreSQL confirmation missing",
            profile_id=profile_id,
            capability="index",
            attributes={
                "store": store,
                "reason": summary["reason"],
            },
        )
        logger.warning(
            "indexing blocked: reason=%s profile=%s store=%s",
            summary["reason"],
            profile_id,
            store,
        )
        return summary
    if store == "postgres" and not settings.is_configured:
        summary = {
            "status": "blocked",
            "reason": "postgres_dsn_missing",
            "profile": profile_id,
            "store": store,
        }
        _emit_indexing_event(
            event="indexing_profile_rejected",
            status=EventStatus.BLOCKED,
            message="Indexing blocked: PostgreSQL DSN missing",
            profile_id=profile_id,
            capability="index",
            attributes={
                "store": store,
                "reason": summary["reason"],
            },
        )
        logger.warning(
            "indexing blocked: reason=%s profile=%s store=%s",
            summary["reason"],
            profile_id,
            store,
        )
        return summary

    manifest_path = normalized_root / "_manifests" / "inventory.json"
    if not manifest_path.exists():
        summary = {
            "status": "blocked",
            "reason": "inventory_manifest_not_found",
            "path": str(manifest_path),
            "profile": profile_id,
            "store": store,
        }
        _emit_indexing_event(
            event="indexing_profile_rejected",
            status=EventStatus.BLOCKED,
            message="Indexing blocked: inventory manifest missing",
            profile_id=profile_id,
            capability="index",
            attributes={
                "store": store,
                "reason": summary["reason"],
                "path": str(manifest_path),
            },
        )
        logger.warning(
            "indexing blocked: reason=%s path=%s profile=%s store=%s",
            summary["reason"],
            manifest_path,
            profile_id,
            store,
        )
        return summary

    inventory = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = inventory.get("records", inventory if isinstance(inventory, list) else [])
    selected = set(only_sources)
    review_decisions = _review_decision_map(normalized_root)
    eligibility_service = IndexingEligibilityService()
    candidates = [
        record
        for record in records
        if not selected or record.get("source_relpath") in selected
    ]
    approved = []
    for record in candidates:
        document_id = str(record.get("document_id") or "")
        decision = review_decisions.get(document_id)
        eligibility = eligibility_service.evaluate(record=record, decision=decision)
        if eligibility.eligible:
            approved.append(record)
            continue

        _emit_indexing_event(
            event="indexing_document_rejected",
            status=EventStatus.REJECTED,
            message="Document rejected for indexing",
            document_id=document_id,
            profile_id=profile_id,
            capability="index",
            attributes={
                "source_relpath": eligibility.source_relpath,
                "reason": eligibility.reason,
                "ingestion_origin": eligibility.ingestion_origin,
            },
        )

    if dry_run:
        summary = {
            "status": "dry_run",
            "profile": profile_id,
            "store": store,
            "ingestion_origin": ingestion_origin,
            "candidate_documents": len(candidates),
            "approved_documents": len(approved),
            "force": force,
        }
        logger.info(
            "indexing dry-run completed: profile=%s store=%s candidates=%s approved=%s",
            profile_id,
            store,
            summary["candidate_documents"],
            summary["approved_documents"],
        )
        return summary

    profile = DEFAULT_PROFILE.model_copy(update={"profile_id": profile_id})
    indexer_kwargs: dict[str, object] = {}
    connection: PostgresConnection | None = None
    if store == "postgres":
        postgres_indexing = _postgres_indexing_components(
            settings=settings,
            profile_id=profile_id,
        )
        blocked = _postgres_live_provider_guard(
            profile=postgres_indexing.profile,
            settings=EmbeddingSettings.from_env(env),
            profile_id=profile_id,
            store=store,
            ingestion_origin=ingestion_origin,
        )
        if blocked is not None:
            _emit_indexing_event(
                event="indexing_profile_rejected",
                status=EventStatus.BLOCKED,
                message="Indexing blocked: profile incompatible with live PostgreSQL lane",
                profile_id=profile_id,
                provider=blocked["embedding_provider"],
                capability="index",
                attributes={
                    "store": store,
                    "reason": blocked["reason"],
                    "embedding_model": blocked["embedding_model"],
                    "vector_table": blocked["vector_table"],
                },
            )
            logger.warning(
                "indexing blocked: reason=%s profile=%s store=%s provider=%s",
                blocked["reason"],
                profile_id,
                store,
                blocked["embedding_provider"],
            )
            finalize_postgres_connection(
                postgres_indexing.connection,
                succeeded=False,
                profile_id=postgres_indexing.profile.profile_id,
                vector_table=postgres_indexing.profile.vector_table,
            )
            return blocked
        profile = _indexing_profile_from_resolved(postgres_indexing.profile)
        _emit_indexing_event(
            event="indexing_profile_resolved",
            status=EventStatus.COMPLETED,
            message="Indexing profile resolved",
            profile_id=profile.profile_id,
            provider=profile.embedding_provider,
            capability="index",
            configuration_hash=postgres_indexing.profile.config_hash,
            attributes={
                "store": store,
                "vector_table": profile.vector_store,
                "ingestion_origin": ingestion_origin,
            },
        )
        indexer_kwargs = postgres_indexing.indexer_kwargs
        indexer_kwargs["storage_mode"] = "postgres"
        indexer_kwargs["ingestion_origin"] = ingestion_origin
        connection = postgres_indexing.connection
    else:
        _emit_indexing_event(
            event="indexing_profile_resolved",
            status=EventStatus.COMPLETED,
            message="Indexing profile resolved",
            profile_id=profile.profile_id,
            provider=profile.embedding_provider,
            capability="index",
            attributes={
                "store": store,
                "vector_store": profile.vector_store,
                "ingestion_origin": ingestion_origin,
            },
        )
    documents = [_indexable_document(record, profile) for record in approved]
    chunks_root = normalized_root.parent / "chunks"
    indexer = LlamaIndexingPort(
        bundle_loader=bundle_loader or FilesystemBundleLoader(chunks_root=chunks_root),
        **indexer_kwargs,
    )
    succeeded = False
    try:
        results = asyncio.run(_index_documents(indexer=indexer, documents=documents))
        succeeded = True
    finally:
        if connection is not None:
            finalize_postgres_connection(
                connection,
                succeeded=succeeded,
                profile_id=profile.profile_id,
                vector_table=profile.vector_store,
            )
    summary = {
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
    logger.info(
        "indexing run completed: profile=%s store=%s documents=%s parents=%s children=%s",
        profile_id,
        store,
        summary["indexed_documents"],
        summary["indexed_parent_nodes"],
        summary["indexed_child_nodes"],
    )
    return summary


def _review_decision_map(normalized_root: Path) -> dict[str, object]:
    review_decisions_path = normalized_root / "_manifests" / "review_decisions.json"
    return {
        decision.document_id: decision
        for decision in load_review_decisions(review_decisions_path)
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
    profile_id: str | None = None,
    vector_table: str | None = None,
) -> None:
    """Finalize a PostgreSQL transaction and close the connection."""

    if succeeded:
        connection.commit()
        _emit_indexing_event(
            event="indexing_persistence_committed",
            status=EventStatus.COMPLETED,
            message="PostgreSQL indexing transaction committed",
            profile_id=profile_id,
            capability="index",
            attributes={
                "store": "postgres",
                "vector_table": vector_table,
            },
        )
    else:
        connection.rollback()
        _emit_indexing_event(
            event="indexing_persistence_rolled_back",
            status=EventStatus.FAILED,
            message="PostgreSQL indexing transaction rolled back",
            profile_id=profile_id,
            capability="index",
            attributes={
                "store": "postgres",
                "vector_table": vector_table,
            },
        )
    connection.close()


def _postgres_live_provider_guard(
    *,
    profile: ResolvedIndexingProfile,
    settings: EmbeddingSettings,
    profile_id: str,
    store: str,
    ingestion_origin: IngestionOrigin,
) -> dict[str, object] | None:
    """Block live PostgreSQL writes for providers outside the production lane."""

    if profile.embedding_provider not in LIVE_POSTGRES_EMBEDDING_PROVIDERS:
        return {
            "status": "blocked",
            "reason": "unsupported_live_embedding_provider",
            "profile": profile_id,
            "store": store,
            "ingestion_origin": ingestion_origin,
            "embedding_provider": profile.embedding_provider,
            "embedding_model": profile.embedding_model,
            "vector_table": profile.vector_table,
            "allowed_providers": sorted(LIVE_POSTGRES_EMBEDDING_PROVIDERS),
        }
    if profile.embedding_provider == "voyage" and settings.voyage_api_key is None:
        return {
            "status": "blocked",
            "reason": "voyage_api_key_missing",
            "profile": profile_id,
            "store": store,
            "ingestion_origin": ingestion_origin,
            "embedding_provider": profile.embedding_provider,
            "embedding_model": profile.embedding_model,
            "vector_table": profile.vector_table,
            "required_secret": "VOYAGE_API_KEY",
        }
    return None


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
