"""Chunk bundle catalog adapters backed by persisted chunking metadata files."""

from __future__ import annotations

import json
from pathlib import Path

from embedding.application.ports import ChunkBundleRepository
from embedding.domain.errors import ChunkBundleNotFound
from embedding.domain.models import ChunkBundleRef

_METADATA_SUFFIX = ".chunking_metadata.json"


def _is_metadata_artifact(artifact_relpath: str) -> bool:
    return artifact_relpath.endswith(_METADATA_SUFFIX)


class FilesystemChunkBundleCatalogRepository:
    """Read chunk bundle references directly from ``data/chunks`` artifacts."""

    def __init__(self, *, chunks_root: Path) -> None:
        self._chunks_root = chunks_root.resolve()

    def get(self, chunk_bundle_id: str) -> ChunkBundleRef:
        for bundle in self.list_bundles():
            if bundle.chunk_bundle_id == chunk_bundle_id:
                return bundle
        raise ChunkBundleNotFound(f"chunk bundle not found: {chunk_bundle_id}")

    def list_bundles(self) -> list[ChunkBundleRef]:
        bundles: list[ChunkBundleRef] = []
        for metadata_path in sorted(self._chunks_root.rglob("*.chunking_metadata.json")):
            bundle = self._load_bundle(metadata_path)
            if bundle is not None:
                bundles.append(bundle)
        return bundles

    def _load_bundle(self, metadata_path: Path) -> ChunkBundleRef | None:
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            project_id = payload.get("project_id")
            variant = payload.get("rag_variant_id")
            recipe = payload.get("semantic_recipe_fingerprint")
            return ChunkBundleRef(
                chunk_bundle_id=str(payload["bundle_fingerprint"]),
                project_id=None if project_id is None else str(project_id),
                bundle_fingerprint=str(payload["bundle_fingerprint"]),
                profile_id=str(payload["profile_id"]),
                profile_fingerprint=str(payload["profile_fingerprint"]),
                corpus_version=str(payload["corpus_version"]),
                source_document_id=str(payload["document_id"]),
                artifact_relpath=metadata_path.relative_to(self._chunks_root).as_posix(),
                source_relpath=str(payload.get("source_relpath") or ""),
                normalized_relpath=str(payload.get("normalized_relpath") or ""),
                source_hash=str(payload.get("source_hash") or ""),
                parent_count=int(payload["parent_count"]),
                child_count=int(payload["child_count"]),
                status="verified",
                # Provenance de variante (Task 6): auditable, nullable.
                rag_variant_id=None if variant is None else str(variant),
                semantic_recipe_fingerprint=None if recipe is None else str(recipe),
            )
        except (KeyError, TypeError, ValueError):
            return None


class HybridChunkBundleRepository:
    """Expose chunk bundles from the durable ledger and live filesystem artifacts."""

    def __init__(
        self,
        *,
        primary: ChunkBundleRepository,
        filesystem: FilesystemChunkBundleCatalogRepository,
    ) -> None:
        self._primary = primary
        self._filesystem = filesystem

    def get(self, chunk_bundle_id: str) -> ChunkBundleRef:
        try:
            bundle = self._primary.get(chunk_bundle_id)
        except ChunkBundleNotFound:
            return self._filesystem.get(chunk_bundle_id)
        if _is_metadata_artifact(bundle.artifact_relpath):
            return bundle
        try:
            return self._filesystem.get(bundle.bundle_fingerprint)
        except ChunkBundleNotFound:
            return bundle

    def list_bundles(self) -> list[ChunkBundleRef]:
        merged: dict[str, ChunkBundleRef] = {}
        for bundle in self._primary.list_bundles():
            visible = self._visible_bundle(bundle)
            if visible is None:
                continue
            merged[visible.bundle_fingerprint] = visible
        for bundle in self._filesystem.list_bundles():
            merged[bundle.bundle_fingerprint] = bundle
        return sorted(merged.values(), key=lambda bundle: bundle.chunk_bundle_id)

    def ensure_registered(self, bundle: ChunkBundleRef) -> ChunkBundleRef:
        return self._primary.ensure_registered(bundle)

    def _visible_bundle(self, bundle: ChunkBundleRef) -> ChunkBundleRef | None:
        if _is_metadata_artifact(bundle.artifact_relpath):
            return bundle
        try:
            return self._filesystem.get(bundle.bundle_fingerprint)
        except ChunkBundleNotFound:
            return None
