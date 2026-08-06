"""Atomic filesystem artifact store for sealed embedding bundles.

Layout, relative to the configured artifact root::

    _staging/<embedding_bundle_id>/{manifest.json,vectors.npy,chunk_map.jsonl}
    <embedding_bundle_id>/{manifest.json,vectors.npy,chunk_map.jsonl}

Staging is written first and promoted with a single ``os.replace`` so a crash can
never publish a half-written bundle. Sealed directories are never overwritten and
only relative paths are stored, so no absolute path ever reaches the database,
the API or a log line.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import numpy as np

from embedding.domain.errors import EmbeddingBundleInvalid


MANIFEST_FILENAME = "manifest.json"
VECTORS_FILENAME = "vectors.npy"
CHUNK_MAP_FILENAME = "chunk_map.jsonl"
STAGING_DIRNAME = "_staging"

#: dtype every published vector artifact is stored with.
VECTOR_DTYPE = "float32"


@dataclass(frozen=True)
class BundleArtifactRefs:
    """Relative artifact locations plus their checksums."""

    vector_artifact_relpath: str
    chunk_map_relpath: str
    manifest_relpath: str
    checksums: dict[str, str] = field(default_factory=dict)
    dtype: str = VECTOR_DTYPE
    shape: str = "0x0"


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class FilesystemEmbeddingBundleArtifactStore:
    """Persist vector artifacts under one root with atomic promotion."""

    root: Path

    def stage(
        self,
        *,
        embedding_bundle_id: str,
        manifest: dict[str, object],
        vectors: Sequence[Sequence[float]],
        chunk_map: Sequence[dict[str, object]],
    ) -> BundleArtifactRefs:
        """Write artifacts into an isolated staging directory.

        Raises:
            EmbeddingBundleInvalid: When the bundle is incomplete or already sealed.
        """

        if len(vectors) != len(chunk_map):
            raise EmbeddingBundleInvalid(
                "vector count and chunk map length must match before sealing"
            )
        if not vectors:
            raise EmbeddingBundleInvalid("cannot seal an embedding bundle with no vectors")
        if self._published_dir(embedding_bundle_id).exists():
            raise EmbeddingBundleInvalid("sealed embedding bundle artifacts already exist")

        staging = self._staging_dir(embedding_bundle_id)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)

        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            raise EmbeddingBundleInvalid("vectors must form a two dimensional matrix")
        np.save(staging / VECTORS_FILENAME, matrix, allow_pickle=False)

        with (staging / CHUNK_MAP_FILENAME).open("w", encoding="utf-8") as handle:
            for row in chunk_map:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")

        checksums = {
            VECTORS_FILENAME: _sha256_file(staging / VECTORS_FILENAME),
            CHUNK_MAP_FILENAME: _sha256_file(staging / CHUNK_MAP_FILENAME),
        }
        shape = f"{matrix.shape[0]}x{matrix.shape[1]}"
        full_manifest = {
            **manifest,
            "embedding_bundle_id": embedding_bundle_id,
            "vector_dtype": VECTOR_DTYPE,
            "vector_shape": shape,
            "vector_count": int(matrix.shape[0]),
            "checksums": checksums,
        }
        (staging / MANIFEST_FILENAME).write_text(
            json.dumps(full_manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        checksums[MANIFEST_FILENAME] = _sha256_file(staging / MANIFEST_FILENAME)

        return BundleArtifactRefs(
            vector_artifact_relpath=f"{embedding_bundle_id}/{VECTORS_FILENAME}",
            chunk_map_relpath=f"{embedding_bundle_id}/{CHUNK_MAP_FILENAME}",
            manifest_relpath=f"{embedding_bundle_id}/{MANIFEST_FILENAME}",
            checksums=checksums,
            dtype=VECTOR_DTYPE,
            shape=shape,
        )

    def promote(self, *, embedding_bundle_id: str) -> BundleArtifactRefs:
        """Atomically publish staged artifacts.

        Raises:
            EmbeddingBundleInvalid: When nothing was staged or the bundle is sealed.
        """

        staging = self._staging_dir(embedding_bundle_id)
        published = self._published_dir(embedding_bundle_id)
        if not staging.exists():
            raise EmbeddingBundleInvalid("no staged artifacts to promote")
        if published.exists():
            raise EmbeddingBundleInvalid("sealed embedding bundle artifacts already exist")
        published.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, published)
        manifest = json.loads((published / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        checksums = {str(key): str(value) for key, value in dict(manifest["checksums"]).items()}
        return BundleArtifactRefs(
            vector_artifact_relpath=f"{embedding_bundle_id}/{VECTORS_FILENAME}",
            chunk_map_relpath=f"{embedding_bundle_id}/{CHUNK_MAP_FILENAME}",
            manifest_relpath=f"{embedding_bundle_id}/{MANIFEST_FILENAME}",
            checksums=checksums,
            dtype=str(manifest["vector_dtype"]),
            shape=str(manifest["vector_shape"]),
        )

    def discard_staging(self, *, embedding_bundle_id: str) -> None:
        """Remove a staging directory left behind by a failed run."""

        staging = self._staging_dir(embedding_bundle_id)
        if staging.exists():
            shutil.rmtree(staging)

    def load_vectors(self, *, vector_artifact_relpath: str) -> list[list[float]]:
        """Read back the dense vectors of a published bundle."""

        path = self._resolve_relpath(vector_artifact_relpath)
        matrix = np.load(path, allow_pickle=False)
        return [[float(value) for value in row] for row in matrix]

    def read_manifest(self, *, embedding_bundle_id: str) -> dict[str, object]:
        """Read the published manifest of one bundle."""

        path = self._published_dir(embedding_bundle_id) / MANIFEST_FILENAME
        if not path.exists():
            raise EmbeddingBundleInvalid("embedding bundle manifest is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def verify_checksums(self, *, embedding_bundle_id: str, expected: dict[str, str]) -> bool:
        """Recompute artifact checksums and compare them with the stored ones."""

        published = self._published_dir(embedding_bundle_id)
        for filename, digest in expected.items():
            candidate = published / filename
            if not candidate.exists() or _sha256_file(candidate) != digest:
                return False
        return True

    def _staging_dir(self, embedding_bundle_id: str) -> Path:
        return self._safe_child(self.root / STAGING_DIRNAME, embedding_bundle_id)

    def _published_dir(self, embedding_bundle_id: str) -> Path:
        return self._safe_child(self.root, embedding_bundle_id)

    def _safe_child(self, parent: Path, name: str) -> Path:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise EmbeddingBundleInvalid("embedding bundle id is not a safe path segment")
        return parent / name

    def _resolve_relpath(self, relpath: str) -> Path:
        candidate = (self.root / relpath).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root):
            raise EmbeddingBundleInvalid("artifact path escapes the artifact root")
        if not candidate.exists():
            raise EmbeddingBundleInvalid("embedding bundle artifact is missing")
        return candidate
