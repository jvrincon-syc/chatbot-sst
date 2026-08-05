from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any

from chunking.application.ports import (
    ChunkBundleRepositoryPort,
    StoredChunkBundleMetadata,
)
from chunking.domain.models import ChunkBundle, NormalizedDocumentBundle


@dataclass(frozen=True)
class FilesystemChunkBundleRepository(ChunkBundleRepositoryPort):
    """Persist chunk bundles under one filesystem root with fail-closed promotion."""

    output_root: Path

    def replace(
        self,
        *,
        document: NormalizedDocumentBundle,
        bundle: ChunkBundle,
    ) -> StoredChunkBundleMetadata:
        parent_path = self.parent_chunks_path(document=document)
        child_path = self.child_chunks_path(document=document)
        metadata_path = self.metadata_path(document=document)
        for path in (parent_path, child_path, metadata_path):
            path.parent.mkdir(parents=True, exist_ok=True)

        parent_stage = parent_path.with_suffix(parent_path.suffix + ".tmp")
        child_stage = child_path.with_suffix(child_path.suffix + ".tmp")
        metadata_stage = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        metadata = StoredChunkBundleMetadata(
            document_id=document.document_id,
            normalized_relpath=document.normalized_relpath,
            profile_id=bundle.profile.profile_id,
            profile_fingerprint=bundle.profile.fingerprint,
            bundle_fingerprint=bundle.fingerprint,
        )
        try:
            self._write_jsonl(parent_stage, [parent.as_payload() for parent in bundle.parents])
            self._write_jsonl(child_stage, [child.as_payload() for child in bundle.children])
            self._write_json(
                metadata_stage,
                {
                    **asdict(metadata),
                    "source_relpath": document.source_relpath,
                    "source_hash": document.source_hash,
                    "corpus_version": document.corpus_version,
                    "parent_count": len(bundle.parents),
                    "child_count": len(bundle.children),
                },
            )
            self._promote_staged_files(
                parent_stage=parent_stage,
                child_stage=child_stage,
                metadata_stage=metadata_stage,
                parent_path=parent_path,
                child_path=child_path,
                metadata_path=metadata_path,
            )
        except Exception:
            for staged in (parent_stage, child_stage, metadata_stage):
                if staged.exists():
                    staged.unlink()
            if not metadata_path.exists():
                for promoted in (parent_path, child_path):
                    if promoted.exists():
                        promoted.unlink()
            raise
        return metadata

    def read_metadata(
        self,
        *,
        document: NormalizedDocumentBundle,
    ) -> StoredChunkBundleMetadata | None:
        metadata_path = self.metadata_path(document=document)
        if not metadata_path.exists():
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return StoredChunkBundleMetadata(
            document_id=str(payload["document_id"]),
            normalized_relpath=str(payload["normalized_relpath"]),
            profile_id=str(payload["profile_id"]),
            profile_fingerprint=str(payload["profile_fingerprint"]),
            bundle_fingerprint=str(payload["bundle_fingerprint"]),
        )

    def parent_chunks_path(self, *, document: NormalizedDocumentBundle) -> Path:
        base = self._artifact_base(document.normalized_relpath)
        return base.parent / f"{base.name}.parent_chunks.jsonl"

    def child_chunks_path(self, *, document: NormalizedDocumentBundle) -> Path:
        base = self._artifact_base(document.normalized_relpath)
        return base.parent / f"{base.name}.child_chunks.jsonl"

    def metadata_path(self, *, document: NormalizedDocumentBundle) -> Path:
        base = self._artifact_base(document.normalized_relpath)
        return base.parent / f"{base.name}.chunking_metadata.json"

    def read_parents(self, *, normalized_relpath: str) -> list[dict[str, Any]]:
        return self._read_jsonl(self._path_for_relpath(normalized_relpath, "parent_chunks"))

    def read_children(self, *, normalized_relpath: str) -> list[dict[str, Any]]:
        return self._read_jsonl(self._path_for_relpath(normalized_relpath, "child_chunks"))

    def find_children_by_parent_id(self, *, parent_id: str) -> list[dict[str, Any]]:
        for child_path in self.output_root.rglob("*.child_chunks.jsonl"):
            rows = self._read_jsonl(child_path)
            matches = [row for row in rows if row.get("parent_id") == parent_id]
            if matches:
                return matches
        return []

    def list_stored_documents(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for metadata_path in sorted(self.output_root.rglob("*.chunking_metadata.json")):
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            items.append(
                {
                    "document_id": str(payload.get("document_id") or ""),
                    "normalized_relpath": str(payload.get("normalized_relpath") or ""),
                    "source_relpath": str(payload.get("source_relpath") or ""),
                    "profile_id": str(payload.get("profile_id") or ""),
                    "parent_count": int(payload.get("parent_count") or 0),
                    "child_count": int(payload.get("child_count") or 0),
                }
            )
        items.sort(
            key=lambda item: (
                item["normalized_relpath"],
                item["document_id"],
            )
        )
        return items

    def _artifact_base(self, normalized_relpath: str) -> Path:
        relative = Path(normalized_relpath)
        stem = relative.with_suffix("")
        return self.output_root / stem

    def _path_for_relpath(self, normalized_relpath: str, suffix: str) -> Path:
        base = self._artifact_base(normalized_relpath)
        extension = "jsonl" if suffix.endswith("chunks") else "json"
        return base.parent / f"{base.name}.{suffix}.{extension}"

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        payload = "\n".join(json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows)
        path.write_text(payload + "\n", encoding="utf-8")

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def _promote_staged_files(
        self,
        *,
        parent_stage: Path,
        child_stage: Path,
        metadata_stage: Path,
        parent_path: Path,
        child_path: Path,
        metadata_path: Path,
    ) -> None:
        if metadata_path.exists():
            metadata_path.unlink()
        os.replace(parent_stage, parent_path)
        os.replace(child_stage, child_path)
        os.replace(metadata_stage, metadata_path)
