from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from ingestion.schemas.common import StrictModel
from indexing.domain.models import IndexingProfile


EmbeddingProviderName = Literal["mock", "bge", "voyage", "cohere"]
IngestionOrigin = Literal["local", "llama_cloud"]
DistanceMetric = Literal["cosine", "l2", "inner_product"]


class ResolvedIndexingProfile(StrictModel):
    """Immutable embedding profile resolved for one corpus lane."""

    profile_id: str = Field(min_length=1)
    ingestion_origin: IngestionOrigin
    chunking_version: str = Field(min_length=1)
    embedding_provider: EmbeddingProviderName
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    distance_metric: DistanceMetric
    vector_table: str = Field(pattern=r"^idx_vec_[a-z0-9_]+$")
    metadata_schema_version: str = Field(min_length=1)
    active: bool
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def resolved_profile_from_indexing_profile(
    profile: IndexingProfile,
    *,
    ingestion_origin: IngestionOrigin,
    distance_metric: DistanceMetric,
    active: bool,
    config_hash: str,
) -> ResolvedIndexingProfile:
    """Resolve a legacy indexing profile into the durable profile contract."""

    return ResolvedIndexingProfile(
        profile_id=profile.profile_id,
        ingestion_origin=ingestion_origin,
        chunking_version=profile.chunking_version,
        embedding_provider=profile.embedding_provider,
        embedding_model=profile.embedding_model,
        embedding_dimension=profile.embedding_dimension,
        distance_metric=distance_metric,
        vector_table=vector_table_name(profile.profile_id),
        metadata_schema_version=profile.metadata_schema_version,
        active=active,
        config_hash=config_hash,
    )


def vector_table_name(profile_id: str) -> str:
    """Return a deterministic, validated vector table name for a profile id."""

    normalized = re.sub(r"[^a-z0-9]+", "_", profile_id.lower()).strip("_")
    normalized = re.sub(r"_+", "_", normalized)
    return f"idx_vec_{normalized}"
