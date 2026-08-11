"""Domain contracts for bundle-first indexing.

Indexing consumes pre-computed vectors. Nothing in this module selects a
provider, loads a model or embeds text; that ownership belongs to Embedding.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from pydantic import Field

from ingestion.schemas.common import StrictModel


#: Values accepted by ``indexing_targets.distance_ops``.
DistanceOps = Literal["vector_cosine_ops", "vector_l2_ops", "vector_ip_ops"]

#: Mapping between the semantic metric and the physical pgvector operator class.
DISTANCE_OPS_BY_METRIC: dict[str, DistanceOps] = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "inner_product": "vector_ip_ops",
}

#: Values accepted by ``indexing_runs.status`` (unchanged since 20260722).
IndexingRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "blocked",
]

#: Values accepted by ``indexing_runs.validation_status``.
IndexingValidationStatus = Literal[
    "pending",
    "passed",
    "failed",
    "legacy_unverified",
    "compatibility_not_proven",
]

#: Values accepted by ``indexing_runs.activation_status``.
IndexingActivationStatus = Literal[
    "pending",
    "active",
    "inactive",
    "rolled_back",
    "blocked",
    "legacy_unverified",
]

#: Values accepted by ``indexing_run_documents.status``.
IndexingRunDocumentStatus = Literal[
    "pending",
    "running",
    "committed",
    "failed",
    "skipped",
    "legacy_unverified",
]


class IndexingTarget(StrictModel):
    """One physical pgvector table plus the operator class it was built with."""

    indexing_target_id: str = Field(min_length=1)
    postgres_schema: str = Field(min_length=1)
    vector_table: str = Field(pattern=r"^idx_vec_[a-z0-9_]+$")
    distance_ops: DistanceOps
    storage_schema_version: str = Field(min_length=1)
    active: bool
    created_at: datetime | None = None
    deprecated_at: datetime | None = None

    def accepts_metric(self, distance_metric: str) -> bool:
        """Return whether this target was built for the given semantic metric."""

        return DISTANCE_OPS_BY_METRIC.get(distance_metric) == self.distance_ops


class IndexingRun(StrictModel):
    """One durable bundle-first indexing run."""

    run_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    status: IndexingRunStatus
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_bundle_id: str | None = None
    embedding_profile_id: str | None = None
    indexing_target_id: str | None = None
    corpus_version: str | None = None
    request_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str | None = None
    validation_status: IndexingValidationStatus = "pending"
    activation_status: IndexingActivationStatus = "pending"
    owner_id: str | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        """Return whether the executor will never touch this run again."""

        return self.status in {"completed", "failed", "cancelled", "blocked"}

    @property
    def is_partially_completed(self) -> bool:
        """Return whether the run committed some documents but not all of them."""

        committed = int(self.summary.get("committed_documents", 0) or 0)
        requested = int(self.summary.get("requested_documents", 0) or 0)
        return self.status == "failed" and 0 < committed < requested


class IndexingRunDocument(StrictModel):
    """Per-document outcome of one bundle-first indexing run."""

    run_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingestion_origin: Literal["local", "llama_cloud"]
    eligibility_status: Literal["included", "excluded", "blocked"]
    eligibility_reason: str
    indexed_parent_nodes: int = Field(default=0, ge=0)
    indexed_child_nodes: int = Field(default=0, ge=0)
    error_code: str | None = None
    source_chunk_bundle_id: str | None = None
    embedding_bundle_id: str | None = None
    status: IndexingRunDocumentStatus = "pending"
    parent_count: int = Field(default=0, ge=0)
    child_count: int = Field(default=0, ge=0)
    vector_count: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    committed_at: datetime | None = None
    internal_error_id: str | None = None


class IndexingNodeRecord(StrictModel):
    """One durable ``indexing_nodes`` row built from a chunk bundle.

    Nodes are adapted from the source chunk bundle without re-chunking, so the
    bundle-first path needs no LlamaIndex node objects at all.

    ``project_id``/``source_chunk_id``/``source_parent_chunk_id`` are nullable and
    only populated on the platform (project-owned) path (Fase 4, ADR-007 §2). On the
    legacy path (``project_id is None``) ``node_id == source chunk id`` byte-for-byte
    and these physical-identity fields stay ``None``, so legacy behaviour is unchanged.
    """

    node_id: str = Field(min_length=1)
    project_id: str | None = None
    document_id: str = Field(min_length=1)
    source_relpath: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingestion_origin: Literal["local", "llama_cloud"]
    node_role: Literal["parent", "child"]
    parent_node_id: str | None = None
    source_chunk_id: str | None = None
    source_parent_chunk_id: str | None = None
    chunk_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    section_path: str | None = None
    text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    chunking_version: str = Field(min_length=1)
    processing_fingerprint: str = Field(min_length=1)
    source_chunk_bundle_id: str | None = None
    chunking_bundle_fingerprint: str | None = None
    corpus_version: str | None = None


class IndexingReadiness(StrictModel):
    """Whether one embedding bundle may be written into a target."""

    embedding_bundle_id: str = Field(min_length=1)
    indexing_target_id: str | None = None
    ready: bool
    blocking_reasons: list[str] = Field(default_factory=list)


class IndexingRetrievalReadiness(StrictModel):
    """Whether an indexed bundle can actually serve retrieval traffic."""

    run_id: str = Field(min_length=1)
    embedding_bundle_id: str | None = None
    indexing_target_id: str | None = None
    corpus_version: str | None = None
    ready: bool
    active_vector_rows: int = Field(default=0, ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)


def indexing_request_fingerprint(*, embedding_bundle_id: str) -> str:
    """Return the deterministic fingerprint of one indexing request payload."""

    payload = json.dumps(
        {"embedding_bundle_id": embedding_bundle_id},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
