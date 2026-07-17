"""Strict canonical schemas and explicit legacy ingestion adapters."""

from ingestion.schemas.adapters import adapt_v1_to_v2
from ingestion.schemas.loader import load_artifact
from ingestion.schemas.manifests import (
    ArtifactHash,
    BundleManifest,
    ErrorItem,
    ErrorManifest,
    InventoryManifest,
    ReviewItem,
    ReviewManifest,
    RunDocument,
    RunManifest,
)

__all__ = [
    "ArtifactHash",
    "BundleManifest",
    "ErrorItem",
    "ErrorManifest",
    "InventoryManifest",
    "ReviewItem",
    "ReviewManifest",
    "RunDocument",
    "RunManifest",
    "adapt_v1_to_v2",
    "load_artifact",
]
