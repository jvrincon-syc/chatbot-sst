"""Public request and response contracts for the Embedding API.

Every field is snake_case. Vectors, chunk text, credentials and absolute paths
are never part of a response model.
"""

from __future__ import annotations

from pydantic import Field

from core.api.http import MAX_PAGE_SIZE
from ingestion.schemas.common import StrictModel


class EmbeddingRunRequestSchema(StrictModel):
    """MVP payload: exactly one chunk bundle and one profile."""

    chunk_bundle_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)


class EmbeddingProfileSchema(StrictModel):
    """Read-only view of one durable embedding profile."""

    profile_id: str
    provider: str
    model: str
    model_revision: str
    dimension: int
    normalization: str
    distance_metric: str
    configuration_fingerprint: str | None
    ingestion_origin: str
    chunking_version: str
    vector_table: str
    default_indexing_target_id: str | None
    active: bool
    document_enabled: bool
    query_enabled: bool
    compatibility_status: str
    deprecated_at: str | None = None
    can_embed_documents: bool
    can_embed_queries: bool


class EmbeddingRuntimeSchema(StrictModel):
    """Operational availability of the engine behind one profile."""

    profile_id: str
    provider: str
    model: str
    runtime_mode: str
    engine_available: bool
    engine_revision_observed: str
    supports_documents: bool
    supports_queries: bool
    blocked_reason: str | None = None


class ChunkBundleSchema(StrictModel):
    """Read-only view of one registered chunk bundle."""

    chunk_bundle_id: str
    bundle_fingerprint: str
    profile_id: str
    corpus_version: str
    source_document_id: str
    parent_count: int
    child_count: int
    status: str


class ChunkBundleSummarySchema(ChunkBundleSchema):
    """Chunk bundle plus the embedding bundles already produced from it."""

    profile_fingerprint: str
    embedding_bundle_ids: list[str] = Field(default_factory=list)


class EmbeddingRunSchema(StrictModel):
    """Durable state of one embedding run."""

    embedding_run_id: str
    idempotency_key: str
    request_fingerprint: str
    source_chunk_bundle_id: str
    embedding_profile_id: str
    configuration_fingerprint: str | None
    runtime_engine: str
    runtime_mode: str
    engine_revision_observed: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    summary: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None
    produced_embedding_bundle_id: str | None = None
    links: dict[str, str] = Field(default_factory=dict)


class EmbeddingBundleSchema(StrictModel):
    """Durable state of one embedding bundle. Never carries vectors."""

    embedding_bundle_id: str
    source_chunk_bundle_id: str
    embedding_profile_id: str
    provider: str
    model: str
    model_revision: str
    dimension: int
    normalization: str
    distance_metric: str
    configuration_fingerprint: str
    corpus_version: str
    bundle_schema_version: str
    source_content_fingerprint: str
    vector_dtype: str | None = None
    vector_shape: str | None = None
    vector_count: int
    checksums: dict[str, str] = Field(default_factory=dict)
    status: str
    validation_status: str
    readiness_status: str
    sealed_at: str | None = None
    links: dict[str, str] = Field(default_factory=dict)


class EmbeddingBundleChunkSchema(StrictModel):
    """One row of the durable chunk map. Never carries a vector."""

    child_chunk_id: str
    parent_chunk_id: str
    document_id: str
    vector_offset: int
    vector_length: int
    vector_checksum: str | None = None
    content_hash: str
    chunk_ordinal: int


class ValidationCheckSchema(StrictModel):
    """One named assertion of a validation report."""

    name: str
    passed: bool
    detail: str = ""


class EmbeddingBundleValidationSchema(StrictModel):
    """Validation verdict for one bundle."""

    embedding_bundle_id: str
    status: str
    validator_version: str
    checks: list[ValidationCheckSchema] = Field(default_factory=list)


class EmbeddingIndexingReadinessSchema(StrictModel):
    """Whether a bundle may be handed to Indexing."""

    embedding_bundle_id: str
    indexing_target_id: str | None = None
    status: str
    blocking_reasons: list[str] = Field(default_factory=list)


class PaginatedProfilesSchema(StrictModel):
    items: list[EmbeddingProfileSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedRuntimeSchema(StrictModel):
    items: list[EmbeddingRuntimeSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedChunkBundlesSchema(StrictModel):
    items: list[ChunkBundleSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedEmbeddingRunsSchema(StrictModel):
    items: list[EmbeddingRunSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedBundleChunksSchema(StrictModel):
    items: list[EmbeddingBundleChunkSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
