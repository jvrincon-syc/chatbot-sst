"""Public request and response contracts for the Retrieval API."""

from __future__ import annotations

from pydantic import Field

from core.api.http import MAX_PAGE_SIZE
from ingestion.schemas.common import StrictModel


class CreateRetrievalProfileSchema(StrictModel):
    """Register one retrieval profile for a generic consumer scope."""

    consumer_scope_type: str = Field(min_length=1)
    consumer_scope_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    indexing_target_id: str = Field(min_length=1)
    lexical_fallback_policy: str = "allowed_when_vector_unavailable"


class ValidateRetrievalSchema(StrictModel):
    """Run a controlled smoke validation against one retrieval profile."""

    retrieval_profile_id: str = Field(min_length=1)


class RetrievalProfileSchema(StrictModel):
    """Read-only view of one retrieval profile."""

    retrieval_profile_id: str
    consumer_scope_type: str
    consumer_scope_id: str
    corpus_version: str
    embedding_profile_id: str
    indexing_target_id: str
    lexical_fallback_policy: str
    active: bool
    validation_status: str
    validated_at: str | None = None
    last_runtime_status: str
    created_at: str | None = None
    deprecated_at: str | None = None


class RetrievalRuntimeSchema(StrictModel):
    """Whether the query engine behind one retrieval profile can run today."""

    retrieval_profile_id: str
    embedding_profile_id: str
    indexing_target_id: str
    query_engine_available: bool
    engine_revision_observed: str
    vector_retrieval_enabled: bool
    lexical_fallback_allowed: bool
    blocked_reason: str | None = None


class RetrievalReadinessSchema(StrictModel):
    """Every precondition retrieval needs, evaluated together."""

    retrieval_profile_id: str
    ready: bool
    active_vector_rows: int = Field(ge=0)
    embedding_bundle_id: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class RetrievalProfileStatusSchema(StrictModel):
    """Profile, runtime and readiness in one payload."""

    profile: RetrievalProfileSchema
    runtime: RetrievalRuntimeSchema
    readiness: RetrievalReadinessSchema


class RetrievalValidationSchema(StrictModel):
    """Result of a controlled smoke validation."""

    retrieval_profile_id: str
    status: str
    validator_version: str
    query_dimension: int | None = None
    candidates_found: int = Field(ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)


class PaginatedRetrievalProfilesSchema(StrictModel):
    items: list[RetrievalProfileSchema]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
