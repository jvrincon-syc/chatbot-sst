"""Public request and response contracts for the bundle-first Indexing API.

The client never chooses a provider, model, dimension, normalization, distance
metric or target: those come from the durable profile.
"""

from __future__ import annotations

from pydantic import Field

from core.api.http import MAX_PAGE_SIZE
from ingestion.schemas.common import StrictModel


class IndexingRunRequestSchema(StrictModel):
    """MVP payload: only the sealed embedding bundle."""

    embedding_bundle_id: str = Field(min_length=1)


class ActivationRequestSchema(StrictModel):
    """Explicit activation of one indexed bundle for a consumer scope."""

    run_id: str = Field(min_length=1)
    consumer_scope_type: str = Field(min_length=1)
    consumer_scope_id: str = Field(min_length=1)
    lexical_fallback_policy: str = "allowed_when_vector_unavailable"


class RollbackRequestSchema(StrictModel):
    """Revert one lane to a bundle that was already validated."""

    current_embedding_bundle_id: str = Field(min_length=1)
    previous_embedding_bundle_id: str = Field(min_length=1)
    consumer_scope_type: str = Field(min_length=1)
    consumer_scope_id: str = Field(min_length=1)


class IndexingTargetSchema(StrictModel):
    """Read-only view of one physical pgvector table."""

    indexing_target_id: str
    postgres_schema: str
    vector_table: str
    distance_ops: str
    storage_schema_version: str
    active: bool
    deprecated_at: str | None = None


class IndexingOverviewSchema(StrictModel):
    """Aggregate state of the bundle-first indexing surface."""

    targets: int = Field(ge=0)
    active_targets: int = Field(ge=0)
    profiles: int = Field(ge=0)
    verified_profiles: int = Field(ge=0)
    sealed_bundles: int = Field(ge=0)
    runs: int = Field(ge=0)
    completed_runs: int = Field(ge=0)
    active_runs: int = Field(ge=0)
    bundle_first_enabled: bool


class IndexingRunSchema(StrictModel):
    """Durable state of one indexing run."""

    run_id: str
    profile_id: str
    status: str
    embedding_bundle_id: str | None = None
    embedding_profile_id: str | None = None
    indexing_target_id: str | None = None
    corpus_version: str | None = None
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    validation_status: str
    activation_status: str
    started_at: str | None = None
    completed_at: str | None = None
    summary: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)


class IndexingRunDocumentSchema(StrictModel):
    """Per-document outcome of one indexing run."""

    document_id: str
    source_relpath: str
    status: str
    eligibility_status: str
    eligibility_reason: str
    source_chunk_bundle_id: str | None = None
    embedding_bundle_id: str | None = None
    parent_count: int
    child_count: int
    vector_count: int
    started_at: str | None = None
    committed_at: str | None = None
    error_code: str | None = None
    internal_error_id: str | None = None


class IndexingRunErrorSchema(StrictModel):
    """One sanitized failure derived from ``indexing_run_documents``."""

    document_id: str
    status: str
    error_code: str | None = None
    internal_error_id: str | None = None


class IndexingRetrievalReadinessSchema(StrictModel):
    """Whether an indexed run can actually serve retrieval traffic."""

    run_id: str
    embedding_bundle_id: str | None = None
    indexing_target_id: str | None = None
    corpus_version: str | None = None
    ready: bool
    active_vector_rows: int = Field(ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)


class ActivationResultSchema(StrictModel):
    """Outcome of one activation or rollback."""

    run_id: str
    embedding_bundle_id: str
    indexing_target_id: str
    retrieval_profile_id: str
    activated_rows: int = Field(ge=0)


class PaginatedTargetsSchema(StrictModel):
    items: list[IndexingTargetSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedIndexingRunsSchema(StrictModel):
    items: list[IndexingRunSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedRunDocumentsSchema(StrictModel):
    items: list[IndexingRunDocumentSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedRunErrorsSchema(StrictModel):
    items: list[IndexingRunErrorSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
