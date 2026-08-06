"""Explicit feature flags for the bundle-first rollout.

The legacy paths stay reachable while every flag is off. Flags are read from the
environment at the composition root only; no domain or application module reads
them directly.
"""

from __future__ import annotations

from collections.abc import Mapping
import os

from ingestion.schemas.common import StrictModel


_TRUE_VALUES = {"1", "true", "yes", "on"}


class FeatureFlags(StrictModel):
    """Rollout switches for embedding, indexing and retrieval."""

    embedding_v2: bool = False
    indexing_bundle_first: bool = False
    retrieval_v1: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "FeatureFlags":
        """Load the flags from ``SST_FEATURE_*`` environment variables."""

        env = os.environ if environ is None else environ
        return cls(
            embedding_v2=_flag(env, "SST_FEATURE_EMBEDDING_V2"),
            indexing_bundle_first=_flag(env, "SST_FEATURE_INDEXING_BUNDLE_FIRST"),
            retrieval_v1=_flag(env, "SST_FEATURE_RETRIEVAL_V1"),
        )


def _flag(environ: Mapping[str, str], key: str) -> bool:
    return (environ.get(key) or "").strip().lower() in _TRUE_VALUES
