from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping

from pydantic import BaseModel, ValidationError

from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.inventory import InventoryRecord
from ingestion.schemas.manifests import (
    BundleManifest,
    ErrorManifest,
    InventoryManifest,
    ReviewManifest,
    RunManifest,
)


_CANONICAL_TOP_LEVEL_MODELS = (
    MetadataArtifact,
    PagesArtifact,
    OcrArtifact,
    TablesArtifact,
    FormsArtifact,
    InventoryManifest,
    RunManifest,
    ReviewManifest,
    ErrorManifest,
    BundleManifest,
    InventoryRecord,
)


def _canonical_data(payload: object) -> dict:
    if isinstance(payload, BaseModel):
        if not isinstance(payload, _CANONICAL_TOP_LEVEL_MODELS):
            raise ValueError("output must be a canonical schema 2.0 model or envelope")
        data = payload.model_dump(mode="json")
        if data.get("schema_version") != "2.0":
            raise ValueError("output must be a canonical schema 2.0 model or envelope")
        return data

    if not isinstance(payload, Mapping) or payload.get("schema_version") != "2.0":
        raise ValueError("output must be a canonical schema 2.0 model or envelope")

    data = dict(payload)
    for model in _CANONICAL_TOP_LEVEL_MODELS:
        try:
            return model.model_validate(data).model_dump(mode="json")
        except ValidationError:
            continue
    raise ValueError("output must be a canonical schema 2.0 model or envelope")


def _write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        descriptor = -1
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temp_path.unlink(missing_ok=True)
        raise


def dump_json_atomic(path: Path, payload: object) -> None:
    data = _canonical_data(payload)
    serialized = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    _write_atomic(Path(path), serialized + "\n")


def write_text_atomic(path: Path, text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("text output must be a string")
    _write_atomic(Path(path), text)


def dump_json(path: Path, payload: object) -> None:
    """Compatibility name; all writes now use canonical atomic output."""

    dump_json_atomic(path, payload)


def write_inventory(path: Path, records: Iterable[InventoryRecord]) -> None:
    materialized = list(records)
    if materialized:
        corpus_version = materialized[0].corpus_version
        pipeline_version = materialized[0].pipeline_version
    else:
        corpus_version = "unknown"
        pipeline_version = "unknown"
    manifest = InventoryManifest(
        schema_version="2.0",
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(),
        corpus_version=corpus_version,
        pipeline_version=pipeline_version,
        records=materialized,
    )
    dump_json_atomic(path, manifest)


def write_review_list(path: Path, documents: List[dict]) -> None:
    payload = {
        "schema_version": "2.0",
        "run_id": "manual",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "items": documents,
    }
    dump_json_atomic(path, payload)
