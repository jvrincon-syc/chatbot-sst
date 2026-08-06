"""Domain contracts for retrieval profiles and retrieval readiness.

``retrieval_profiles`` is the authority over activation. The ``is_active``
columns of the ``idx_vec_*`` tables are an operational projection of that
decision, never the decision itself.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import Field

from embedding.domain.models import canonical_json
from ingestion.schemas.common import StrictModel


#: Values accepted by ``retrieval_profiles.validation_status``.
RetrievalValidationStatus = Literal["pending", "passed", "failed", "compatibility_not_proven"]

#: Values accepted by ``retrieval_profiles.last_runtime_status``.
RetrievalRuntimeState = Literal["never_run", "ok", "failed", "blocked"]

#: Policies that decide whether lexical retrieval may answer alone.
LexicalFallbackPolicy = Literal[
    "allowed_when_vector_unavailable",
    "never",
    "always",
]

#: Version stamped on retrieval readiness checks.
RETRIEVAL_VALIDATOR_VERSION = "retrieval-validator-v1"


class RetrievalProfile(StrictModel):
    """One consumer scope bound to exactly one embedding profile and target."""

    retrieval_profile_id: str = Field(min_length=1)
    consumer_scope_type: str = Field(min_length=1)
    consumer_scope_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    indexing_target_id: str = Field(min_length=1)
    lexical_fallback_policy: LexicalFallbackPolicy = "allowed_when_vector_unavailable"
    active: bool = False
    validation_status: RetrievalValidationStatus = "pending"
    validated_at: datetime | None = None
    last_runtime_status: RetrievalRuntimeState = "never_run"
    created_at: datetime | None = None
    deprecated_at: datetime | None = None

    @property
    def is_usable(self) -> bool:
        """Return whether this profile may serve retrieval traffic."""

        return (
            self.active
            and self.validation_status == "passed"
            and self.deprecated_at is None
        )

    @classmethod
    def build(
        cls,
        *,
        consumer_scope_type: str,
        consumer_scope_id: str,
        corpus_version: str,
        embedding_profile_id: str,
        indexing_target_id: str,
        lexical_fallback_policy: str = "allowed_when_vector_unavailable",
    ) -> "RetrievalProfile":
        """Build an inactive profile with a deterministic identifier."""

        digest = sha256(
            canonical_json(
                [
                    consumer_scope_type,
                    consumer_scope_id,
                    corpus_version,
                    embedding_profile_id,
                    indexing_target_id,
                ]
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            retrieval_profile_id=f"retrieval-profile-{digest}",
            consumer_scope_type=consumer_scope_type,
            consumer_scope_id=consumer_scope_id,
            corpus_version=corpus_version,
            embedding_profile_id=embedding_profile_id,
            indexing_target_id=indexing_target_id,
            lexical_fallback_policy=lexical_fallback_policy,  # type: ignore[arg-type]
        )


class RetrievalRuntimeStatus(StrictModel):
    """Whether the query engine behind one retrieval profile can run today."""

    retrieval_profile_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    indexing_target_id: str = Field(min_length=1)
    query_engine_available: bool
    engine_revision_observed: str
    vector_retrieval_enabled: bool
    lexical_fallback_allowed: bool
    blocked_reason: str | None = None


class RetrievalReadiness(StrictModel):
    """Every precondition retrieval needs, evaluated together."""

    retrieval_profile_id: str = Field(min_length=1)
    ready: bool
    active_vector_rows: int = Field(default=0, ge=0)
    embedding_bundle_id: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class RetrievalValidation(StrictModel):
    """Result of a controlled smoke validation against a retrieval profile."""

    retrieval_profile_id: str = Field(min_length=1)
    status: Literal["passed", "failed", "blocked"]
    validator_version: str = RETRIEVAL_VALIDATOR_VERSION
    query_dimension: int | None = None
    candidates_found: int = Field(default=0, ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)


class RetrievedEvidence(StrictModel):
    """One retrieved child chunk with the provenance the answer must cite."""

    node_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    parent_node_id: str | None = None
    child_chunk_id: str = Field(min_length=1)
    text: str
    score: float
    source: Literal["vector", "lexical"]
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    section_path: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    embedding_profile_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    embedding_bundle_id: str | None = None
