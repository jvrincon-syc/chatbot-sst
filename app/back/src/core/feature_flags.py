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
_FALSE_VALUES = {"0", "false", "no", "off"}


class FeatureFlags(StrictModel):
    """Rollout switches for embedding, indexing and retrieval."""

    embedding_v2: bool = True
    indexing_bundle_first: bool = True
    retrieval_v1: bool = True

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "FeatureFlags":
        """Load the flags from ``SST_FEATURE_*`` environment variables."""

        env = os.environ if environ is None else environ
        return cls(
            embedding_v2=_flag(
                env,
                "SST_FEATURE_EMBEDDING_V2",
                default=cls.model_fields["embedding_v2"].default,
            ),
            indexing_bundle_first=_flag(
                env,
                "SST_FEATURE_INDEXING_BUNDLE_FIRST",
                default=cls.model_fields["indexing_bundle_first"].default,
            ),
            retrieval_v1=_flag(
                env,
                "SST_FEATURE_RETRIEVAL_V1",
                default=cls.model_fields["retrieval_v1"].default,
            ),
        )


def _flag(environ: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw = (environ.get(key) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default
