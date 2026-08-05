from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from core.logging.logger import configure_structured_logging  # noqa: E402


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local structural chunking.")
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--chunks-root", default="data/chunks")
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--profile", default="local-structural-v1")
    return parser.parse_args()


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()
    logger.info(
        "chunking_command_started",
        extra={
            "stage": "chunking",
            "event": "chunking_command_started",
            "status": "started",
            "docs_normalized": args.docs_normalized,
            "chunks_root": args.chunks_root,
            "profile": args.profile,
        },
    )
    docs_root = Path(args.docs_normalized)
    chunks_root = Path(args.chunks_root)
    profile = _profile(args.profile)
    source = Schema2NormalizedDocumentSource(docs_normalized=docs_root)
    orchestrator = ChunkingOrchestrator(
        engine=LocalChunkingEngine(),
        bundle_repository=FilesystemChunkBundleRepository(output_root=chunks_root),
        run_repository=FilesystemRunRepository(output_root=chunks_root),
    )
    documents = args.document or _discover_documents(docs_root)
    results = []
    for relative_markdown_path in documents:
        document = source.load(relative_markdown_path)
        result = orchestrator.process_document(document=document, profile=profile)
        logger.info(
            "Chunked normalized document",
            extra={
                "document_id": result.document_id,
                "run_id": result.run_id,
                "reused": result.reused,
            },
        )
        results.append(
            {
                "document_id": result.document_id,
                "run_id": result.run_id,
                "reused": result.reused,
                "bundle_fingerprint": result.bundle_fingerprint,
                "profile_fingerprint": result.profile_fingerprint,
                "status": result.validation.status,
                "parent_count": result.validation.parent_count,
                "child_count": result.validation.child_count,
            }
        )
    logger.info(
        "chunking_command_completed",
        extra={
            "stage": "chunking",
            "event": "chunking_command_completed",
            "status": "completed",
            "document_count": len(results),
            "docs_normalized": args.docs_normalized,
            "chunks_root": args.chunks_root,
            "profile": args.profile,
        },
    )
    print(json.dumps({"documents": results}, ensure_ascii=False, sort_keys=True))
    return 0


def _profile(profile_id: str) -> ChunkingProfile:
    if profile_id != "local-structural-v1":
        raise ValueError(f"unsupported local chunking profile: {profile_id}")
    return ChunkingProfile.local_structural_v1()


def _discover_documents(docs_root: Path) -> list[str]:
    return sorted(
        path.relative_to(docs_root).as_posix()
        for path in docs_root.rglob("*.md")
        if "_manifests" not in path.parts
    )


if __name__ == "__main__":
    raise SystemExit(main())
