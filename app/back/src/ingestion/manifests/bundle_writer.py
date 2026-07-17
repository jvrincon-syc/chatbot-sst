from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel

from ingestion.manifests.writer import dump_json_atomic, write_text_atomic
from ingestion.paths import ArtifactPaths, canonical_relpath, stable_document_id
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
    for value in artifact_relpaths:
        relpath = canonical_relpath(value)
        content = (root / Path(relpath)).read_bytes()
        hashes.append(
            ArtifactHash(
                relpath=relpath,
                sha256=hashlib.sha256(content).hexdigest(),
                byte_size=len(content),
            )
        )
    return hashes


def _validate_bundle_payload(payload: BundlePayload) -> tuple[ArtifactPaths, tuple[str, ...]]:
    source_relpath = canonical_relpath(payload.source_relpath)
    if payload.document_id != stable_document_id(source_relpath):
        raise ValueError("bundle document ID does not match its source relpath")

    paths = ArtifactPaths.for_source(source_relpath)
    required = paths.required_relpaths()
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
            ArtifactHash(relpath=relpath, sha256="0" * 64, byte_size=0)
            for relpath in required
        ],
        processing_fingerprint=payload.processing_fingerprint,
        document_status=payload.document_status,
    )
    return paths, required


def write_bundle_atomic(
    candidate_root: Path,
    bundle_payload: BundlePayload | Mapping[str, object],
) -> BundleManifest:
    payload = _coerce_bundle_payload(bundle_payload)
    paths, required = _validate_bundle_payload(payload)
    root = Path(candidate_root)
    root.mkdir(parents=True, exist_ok=True)

    unexpected = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in set(required)
    ]
    if unexpected:
        raise ValueError("candidate root contains files outside the required artifact set")

    for relpath in required:
        target = root / Path(relpath)
        artifact = payload.artifacts[relpath]
        if relpath == paths.markdown:
            write_text_atomic(target, artifact)
        else:
            dump_json_atomic(target, artifact)

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
