from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ingestion.paths import ArtifactPaths, stable_document_id
from indexing.application.use_cases.index_document import IndexDocumentUseCase
from indexing.domain.models import IndexingProfile
from indexing.domain.models import IndexableDocument, NormalizedArtifactRefs
from indexing.infrastructure.llama_index.pipeline_factory import (
    BundleLoader,
    FilesystemBundleLoader,
    LlamaIndexingPort,
)


DEFAULT_PROFILE = IndexingProfile(
    profile_id="llama-first-local-v1",
    chunking_version="structure-aware-v1",
    embedding_provider="mock",
    embedding_model="deterministic",
    embedding_dimension=384,
    vector_store="memory",
    metadata_schema_version="2.0",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Llama-first indexing.")
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--only-source", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.profile_id)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_indexing(
        normalized_root=Path(args.docs_normalized),
        only_sources=args.only_source,
        force=args.force,
        profile_id=args.profile,
        dry_run=args.dry_run,
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
) -> dict:
    manifest_path = normalized_root / "_manifests" / "inventory.json"
    if not manifest_path.exists():
        return {
            "status": "blocked",
            "reason": "inventory_manifest_not_found",
            "path": str(manifest_path),
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
            "candidate_documents": len(candidates),
            "approved_documents": len(approved),
            "force": force,
        }

    profile = DEFAULT_PROFILE.model_copy(update={"profile_id": profile_id})
    documents = [_indexable_document(record, profile) for record in approved]
    indexer = LlamaIndexingPort(
        bundle_loader=bundle_loader or FilesystemBundleLoader(normalized_root=normalized_root)
    )
    results = asyncio.run(_index_documents(indexer=indexer, documents=documents))
    return {
        "status": "indexed",
        "profile": profile_id,
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
