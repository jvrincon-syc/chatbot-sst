from __future__ import annotations

from typing import Any, Mapping, Optional

from ingestion.schemas.adapters import adapt_v1_to_v2
from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.inventory import InventoryRecord


_CANONICAL_MODELS = {
    "metadata": MetadataArtifact,
    "pages": PagesArtifact,
    "ocr": OcrArtifact,
    "tables": TablesArtifact,
    "forms": FormsArtifact,
    "inventory": InventoryRecord,
    "inventoryrecord": InventoryRecord,
}


def _normalize_artifact_type(artifact_type: Any) -> str:
    if isinstance(artifact_type, str):
        name = artifact_type
    elif isinstance(artifact_type, type):
        name = artifact_type.__name__
    else:
        raise ValueError(f"unknown artifact_type: {artifact_type!r}")
    return name.lower().removesuffix("artifact")


def load_artifact(
    payload: Mapping[str, Any],
    artifact_type: Any,
    context: Optional[Mapping[str, Any]] = None,
):
    """Load only explicitly versioned payloads, adapting 1.0 to canonical 2.0."""

    version = payload.get("schema_version")
    if version not in {"1.0", "2.0"}:
        raise ValueError(
            "schema_version must be explicitly set to supported version '1.0' or '2.0'"
        )
    normalized_type = _normalize_artifact_type(artifact_type)
    model = _CANONICAL_MODELS.get(normalized_type)
    if model is None:
        raise ValueError(f"unknown artifact_type: {artifact_type!r}")
    if version == "1.0":
        return adapt_v1_to_v2(payload, normalized_type, context or {})
    return model.model_validate(payload)
