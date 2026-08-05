from __future__ import annotations

import json
from pathlib import Path

from chunking.application.chunking_orchestrator import ChunkingRunResult, RunRepositoryPort
from chunking.application.ports import StoredChunkBundleMetadata


class FilesystemRunRepository(RunRepositoryPort):
    """Persist chunking run manifests and validation summaries on disk."""

    def __init__(self, output_root: Path) -> None:
        self._manifest_root = output_root / "_manifests"

    def record(
        self,
        *,
        result: ChunkingRunResult,
        metadata: StoredChunkBundleMetadata,
    ) -> None:
        self._manifest_root.mkdir(parents=True, exist_ok=True)
        manifest_path = self._manifest_root / f"{result.run_id}.json"
        validation_path = self._manifest_root / f"{result.run_id}.validation.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "document_id": result.document_id,
                    "reused": result.reused,
                    "bundle_fingerprint": result.bundle_fingerprint,
                    "profile_fingerprint": result.profile_fingerprint,
                    "profile_id": metadata.profile_id,
                    "normalized_relpath": metadata.normalized_relpath,
                    "status": result.validation.status,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        validation_path.write_text(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "document_id": result.document_id,
                    "status": result.validation.status,
                    "parent_count": result.validation.parent_count,
                    "child_count": result.validation.child_count,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
