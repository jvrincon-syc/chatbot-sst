"""Strict canonical schemas and explicit legacy ingestion adapters."""

from ingestion.schemas.adapters import adapt_v1_to_v2
from ingestion.schemas.loader import load_artifact

__all__ = ["adapt_v1_to_v2", "load_artifact"]
