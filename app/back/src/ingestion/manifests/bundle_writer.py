from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel

from ingestion.paths import ArtifactPaths, canonical_relpath, stable_document_id
from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.manifests import ArtifactHash, BundleManifest, DocumentStatus


@dataclass
class BundlePayload:
    document_id: str
    source_relpath: str
    source_hash: str
    processing_fingerprint: str
    document_status: DocumentStatus
    artifacts: Mapping[str, object]


def _coerce_bundle_payload(
    payload: BundlePayload | Mapping[str, object],
) -> BundlePayload:
    if isinstance(payload, BundlePayload):
        return payload
    if not isinstance(payload, Mapping):
        raise TypeError("bundle payload must be BundlePayload or a mapping")
    required_fields = {
        "document_id",
        "source_relpath",
        "source_hash",
        "processing_fingerprint",
        "document_status",
        "artifacts",
    }
    if set(payload) != required_fields:
        raise ValueError("bundle payload fields do not match the strict contract")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, Mapping):
        raise TypeError("bundle artifacts must be a mapping")
    return BundlePayload(
        document_id=payload["document_id"],
        source_relpath=payload["source_relpath"],
        source_hash=payload["source_hash"],
        processing_fingerprint=payload["processing_fingerprint"],
        document_status=payload["document_status"],
        artifacts=artifacts,
    )


def compute_artifact_hashes(
    candidate_root: Path,
    artifact_relpaths: list[str] | tuple[str, ...],
) -> list[ArtifactHash]:
    root = Path(candidate_root)
    hashes: list[ArtifactHash] = []
    root_fd = _open_root_fd(root)
    try:
        for value in artifact_relpaths:
            relpath = canonical_relpath(value)
            content = _read_bytes_secure(root_fd, relpath)
            if content is None:
                raise FileNotFoundError(relpath)
            hashes.append(
                ArtifactHash(
                    schema_version="2.0",
                    relpath=relpath,
                    sha256=hashlib.sha256(content).hexdigest(),
                    byte_size=len(content),
                )
            )
    finally:
        os.close(root_fd)
    return hashes


def _expected_artifact_types(paths: ArtifactPaths) -> dict[str, type[BaseModel]]:
    return {
        paths.metadata: MetadataArtifact,
        paths.pages: PagesArtifact,
        paths.ocr: OcrArtifact,
        paths.tables: TablesArtifact,
        paths.forms: FormsArtifact,
    }


def _validate_bundle_payload(payload: BundlePayload) -> tuple[ArtifactPaths, tuple[str, ...]]:
    source_relpath = canonical_relpath(payload.source_relpath)
    if payload.document_id != stable_document_id(source_relpath):
        raise ValueError("bundle document ID does not match its source relpath")

    paths = ArtifactPaths.for_source(source_relpath)
    required = paths.required_relpaths()
    expected_types = _expected_artifact_types(paths)
    artifact_relpaths = tuple(canonical_relpath(value) for value in payload.artifacts)
    if set(artifact_relpaths) != set(required) or len(artifact_relpaths) != len(required):
        raise ValueError("bundle artifacts must be exactly the required artifact set")

    if not isinstance(payload.artifacts[paths.markdown], str):
        raise TypeError("the normalized Markdown artifact must be text")

    for relpath in required:
        if relpath == paths.markdown:
            continue
        artifact = payload.artifacts[relpath]
        if not isinstance(artifact, BaseModel):
            raise TypeError("JSON bundle artifacts must be canonical schema models")
        expected_type = expected_types[relpath]
        if not isinstance(artifact, expected_type):
            raise TypeError(
                f"artifact {relpath!r} must be {expected_type.__name__}"
            )
        artifact_document_id = getattr(artifact, "document_id", None)
        if artifact_document_id != payload.document_id:
            raise ValueError(
                f"artifact document ID disagrees with bundle document ID: {relpath!r}"
            )
        if getattr(artifact, "schema_version", None) != "2.0":
            raise ValueError("bundle artifacts must use canonical schema 2.0")

    BundleManifest(
        schema_version="2.0",
        document_id=payload.document_id,
        source_relpath=paths.source_relpath,
        source_hash=payload.source_hash,
        normalized_base=paths.normalized_base,
        required_artifacts=list(required),
        artifact_hashes=[
            ArtifactHash(
                schema_version="2.0",
                relpath=relpath,
                sha256="0" * 64,
                byte_size=0,
            )
            for relpath in required
        ],
        processing_fingerprint=payload.processing_fingerprint,
        document_status=payload.document_status,
    )
    return paths, required


def _snapshot_targets(root: Path, relpaths: tuple[str, ...]) -> dict[Path, bytes | None]:
    snapshots: dict[Path, bytes | None] = {}
    root_fd = _open_root_fd(root)
    try:
        for relpath in relpaths:
            target = root / Path(canonical_relpath(relpath))
            snapshots[target] = _read_bytes_secure(root_fd, relpath)
    finally:
        os.close(root_fd)
    return snapshots


def _open_root_fd(root: Path) -> int:
    if root.is_symlink():
        raise ValueError("candidate root must not be a symlink")
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _open_parent_fd(
    root_fd: int,
    relpath: str,
    *,
    create: bool,
) -> tuple[int | None, str]:
    parts = canonical_relpath(relpath).split("/")
    leaf = parts[-1]
    current_fd = os.dup(root_fd)
    for part in parts[:-1]:
        try:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=current_fd)
                except FileExistsError:
                    pass
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
        except FileNotFoundError:
            os.close(current_fd)
            return None, leaf
        except OSError as exc:
            os.close(current_fd)
            raise ValueError("artifact target escapes candidate root") from exc
        os.close(current_fd)
        current_fd = next_fd
    return current_fd, leaf


def _read_bytes_secure(root_fd: int, relpath: str) -> bytes | None:
    parent_fd, leaf = _open_parent_fd(root_fd, relpath, create=False)
    if parent_fd is None:
        return None
    try:
        try:
            file_fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ValueError("artifact target escapes candidate root") from exc
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(file_fd)
    finally:
        os.close(parent_fd)


def _write_bytes_secure(root_fd: int, relpath: str, content: bytes) -> None:
    parent_fd, leaf = _open_parent_fd(root_fd, relpath, create=True)
    if parent_fd is None:
        raise FileNotFoundError(relpath)
    temp_name = f".{leaf}.{uuid.uuid4().hex}.tmp"
    temp_created = False
    try:
        file_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            mode=0o600,
            dir_fd=parent_fd,
        )
        temp_created = True
        try:
            view = memoryview(content)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.replace(temp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        temp_created = False
    finally:
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _write_text_secure(root_fd: int, relpath: str, text: str) -> None:
    _write_bytes_secure(root_fd, relpath, text.encode("utf-8"))


def _unlink_secure(root_fd: int, relpath: str) -> None:
    parent_fd, leaf = _open_parent_fd(root_fd, relpath, create=False)
    if parent_fd is None:
        return
    try:
        try:
            os.unlink(leaf, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(parent_fd)


def _artifact_text(artifact: object) -> str:
    if isinstance(artifact, str):
        return artifact
    if not isinstance(artifact, BaseModel):
        raise TypeError("JSON bundle artifacts must be canonical schema models")
    return (
        json.dumps(
            artifact.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _cleanup_empty_parents(root: Path, target: Path) -> None:
    parent = target.parent
    root = root.resolve()
    while parent != root and root in parent.resolve().parents:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _restore_snapshots(root: Path, snapshots: Mapping[Path, bytes | None]) -> None:
    root_fd = _open_root_fd(root)
    try:
        for target, content in snapshots.items():
            relpath = target.relative_to(root).as_posix()
            if content is None:
                _unlink_secure(root_fd, relpath)
                _cleanup_empty_parents(root, target)
            else:
                _write_bytes_secure(root_fd, relpath, content)
    finally:
        os.close(root_fd)


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("candidate root contains symlinks")


def write_bundle_atomic(
    candidate_root: Path,
    bundle_payload: BundlePayload | Mapping[str, object],
) -> BundleManifest:
    payload = _coerce_bundle_payload(bundle_payload)
    paths, required = _validate_bundle_payload(payload)
    root = Path(candidate_root)
    root.mkdir(parents=True, exist_ok=True)
    _reject_symlinks(root)

    unexpected = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in set(required)
    ]
    if unexpected:
        raise ValueError("candidate root contains files outside the required artifact set")

    snapshots = _snapshot_targets(root, required)
    try:
        root_fd = _open_root_fd(root)
        try:
            for relpath in required:
                _write_text_secure(root_fd, relpath, _artifact_text(payload.artifacts[relpath]))
        finally:
            os.close(root_fd)
    except BaseException:
        _restore_snapshots(root, snapshots)
        raise

    artifact_hashes = compute_artifact_hashes(root, required)
    return BundleManifest(
        schema_version="2.0",
        document_id=payload.document_id,
        source_relpath=paths.source_relpath,
        source_hash=payload.source_hash,
        normalized_base=paths.normalized_base,
        required_artifacts=list(required),
        artifact_hashes=artifact_hashes,
        processing_fingerprint=payload.processing_fingerprint,
        document_status=payload.document_status,
    )
