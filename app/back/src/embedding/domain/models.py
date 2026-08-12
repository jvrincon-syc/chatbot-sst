"""Neutral domain contracts for embedding runs, bundles and compatibility.

These models mirror the frozen persistence contract introduced by migrations
``20260805_01`` .. ``20260805_15``. Enum literals are the exact values accepted
by the SQL ``CHECK`` constraints; nothing here invents a state the database
cannot store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal, Mapping, Sequence

from pydantic import Field

from ingestion.schemas.common import StrictModel


#: Values accepted by ``indexing_profiles.normalization``.
Normalization = Literal[
    "unknown_normalization",
    "none",
    "l2",
    "provider_normalized",
]

#: Values accepted by ``indexing_profiles.distance_metric``.
DistanceMetric = Literal["cosine", "l2", "inner_product"]

#: Values accepted by ``indexing_profiles.compatibility_status``.
CompatibilityStatus = Literal[
    "verified",
    "legacy_unverified",
    "compatibility_not_proven",
]

#: Values accepted by ``embedding_runs.status``.
EmbeddingRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "blocked",
]

#: Values accepted by ``embedding_runs.runtime_mode``.
EmbeddingRuntimeMode = Literal["local", "cloud", "dry_run", "legacy"]

#: Values accepted by ``embedding_bundles.status``.
EmbeddingBundleStatus = Literal["pending", "sealed", "failed", "legacy_unverified"]

#: Values accepted by ``embedding_bundles.validation_status``.
BundleValidationStatus = Literal[
    "pending",
    "passed",
    "failed",
    "legacy_unverified",
    "compatibility_not_proven",
]

#: Values accepted by ``embedding_bundles.readiness_status``.
BundleReadinessStatus = Literal[
    "pending",
    "ready",
    "blocked",
    "legacy_unverified",
    "compatibility_not_proven",
]

#: Values accepted by ``readiness_checks.status``.
ReadinessCheckStatus = Literal["pending", "passed", "failed", "blocked", "legacy_unverified"]

#: Values accepted by ``readiness_checks.check_kind``.
ReadinessCheckKind = Literal[
    "embedding_bundle_validation",
    "embedding_profile_verification",
    "indexing_readiness",
    "retrieval_readiness",
]

#: Sentinel stored by ``20260805_01`` when a revision was never observed.
UNKNOWN_REVISION = "unknown_revision"

#: Version stamped on every readiness check written by this backend.
VALIDATOR_VERSION = "embedding-validator-v1"

#: Schema version stamped on every bundle produced by this backend.
BUNDLE_SCHEMA_VERSION = "embedding-bundle-v1"

#: Narrow operational waivers for legacy profiles that must stay usable while
#: their durable compatibility metadata is still incomplete.
_OPERATIONAL_COMPATIBILITY_WAIVERS = frozenset(
    {
        ("bge", "BAAI/bge-m3", 1024),
    }
)


def canonical_json(payload: object) -> str:
    """Serialize a payload deterministically for hashing.

    Args:
        payload: Any JSON-serializable value.

    Returns:
        A stable, sorted, ASCII JSON representation.
    """

    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EmbeddingConfigurationFingerprint:
    """Deterministic digest of the semantic embedding configuration.

    Only semantic fields participate. Operational settings (credentials,
    timeouts, batch size, device, concurrency) are deliberately excluded so that
    the environment can never change the identity of a vector space.
    """

    value: str

    def __post_init__(self) -> None:
        if len(self.value) != 64 or any(char not in "0123456789abcdef" for char in self.value):
            raise ValueError("configuration fingerprint must be a lowercase sha256 hex digest")

    @classmethod
    def compute(
        cls,
        *,
        provider: str,
        model: str,
        model_revision: str,
        dimension: int,
        normalization: Normalization,
        distance_metric: DistanceMetric,
        semantic_config: Mapping[str, object],
    ) -> "EmbeddingConfigurationFingerprint":
        """Recompute the semantic fingerprint from durable profile fields."""

        digest = sha256(
            canonical_json(
                {
                    "provider": provider,
                    "model": model,
                    "model_revision": model_revision,
                    "dimension": dimension,
                    "normalization": normalization,
                    "distance_metric": distance_metric,
                    "semantic_config": dict(semantic_config),
                }
            ).encode("utf-8")
        ).hexdigest()
        return cls(value=digest)


class EmbeddingProfile(StrictModel):
    """Durable semantic embedding contract read from ``indexing_profiles``."""

    profile_id: str = Field(min_length=1)
    ingestion_origin: Literal["local", "llama_cloud"]
    chunking_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    normalization: Normalization
    distance_metric: DistanceMetric
    configuration_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    semantic_config: dict[str, object] = Field(default_factory=dict)
    vector_table: str = Field(pattern=r"^idx_vec_[a-z0-9_]+$")
    metadata_schema_version: str = Field(min_length=1)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    default_indexing_target_id: str | None = None
    active: bool
    document_enabled: bool
    query_enabled: bool
    compatibility_status: CompatibilityStatus
    deprecated_at: datetime | None = None

    @property
    def is_verified(self) -> bool:
        """Return whether the profile passed an explicit compatibility check."""

        return self.compatibility_status == "verified" and self.deprecated_at is None

    @property
    def has_operational_compatibility_waiver(self) -> bool:
        """Return whether one narrow legacy waiver keeps the profile usable."""

        return self.deprecated_at is None and (
            self.provider,
            self.model,
            self.dimension,
        ) in _OPERATIONAL_COMPATIBILITY_WAIVERS

    @property
    def compatibility_gate_open(self) -> bool:
        """Return whether the profile may pass operational compatibility gates."""

        return self.is_verified or self.has_operational_compatibility_waiver

    def normalization_matches_runtime(self, observed: Normalization) -> bool:
        """Return whether one runtime normalization is compatible with the profile."""

        if self.normalization == observed:
            return True
        return (
            self.has_operational_compatibility_waiver
            and self.normalization == "unknown_normalization"
            and observed == "l2"
        )

    @property
    def can_embed_documents(self) -> bool:
        """Return whether the profile may produce document vectors."""

        return self.active and (
            (self.document_enabled and self.compatibility_gate_open)
            or self.has_operational_compatibility_waiver
        )

    @property
    def can_embed_queries(self) -> bool:
        """Return whether the profile may produce query vectors."""

        return self.active and (
            (self.query_enabled and self.compatibility_gate_open)
            or self.has_operational_compatibility_waiver
        )

    def expected_fingerprint(self) -> EmbeddingConfigurationFingerprint:
        """Recompute the semantic fingerprint implied by this profile row."""

        return EmbeddingConfigurationFingerprint.compute(
            provider=self.provider,
            model=self.model,
            model_revision=self.model_revision,
            dimension=self.dimension,
            normalization=self.normalization,
            distance_metric=self.distance_metric,
            semantic_config=self.semantic_config,
        )


class CompatibilityMismatch(StrictModel):
    """One semantic field that failed strong compatibility."""

    field_name: str = Field(min_length=1)
    expected: str
    observed: str


class CompatibilityReport(StrictModel):
    """Outcome of comparing a durable profile against a live engine."""

    profile_id: str = Field(min_length=1)
    compatible: bool
    mismatches: list[CompatibilityMismatch] = Field(default_factory=list)
    revision_source: Literal["engine_observed", "operator_attestation", "unproven"] = "unproven"

    @classmethod
    def failed(
        cls,
        *,
        profile_id: str,
        mismatches: Sequence[CompatibilityMismatch],
        revision_source: Literal["engine_observed", "operator_attestation", "unproven"] = "unproven",
    ) -> "CompatibilityReport":
        """Build a failing report."""

        return cls(
            profile_id=profile_id,
            compatible=False,
            mismatches=list(mismatches),
            revision_source=revision_source,
        )


class EmbeddingRuntimeStatus(StrictModel):
    """Operational availability of the engine behind one durable profile."""

    profile_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    runtime_mode: EmbeddingRuntimeMode
    engine_available: bool
    engine_revision_observed: str = UNKNOWN_REVISION
    supports_documents: bool
    supports_queries: bool
    blocked_reason: str | None = None


class EmbeddingRun(StrictModel):
    """One durable embedding run over a single source chunk bundle."""

    embedding_run_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_chunk_bundle_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    configuration_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # Contexto de release (Fase 4, gap #1/#2): nullable, derivado por el servidor
    # desde un build context validado, nunca del payload. Legacy escribe NULL.
    # No forma parte de la identidad del run ni del bundle producido (ADR-007).
    project_id: str | None = None
    rag_variant_id: str | None = None
    rag_release_id: str | None = None
    runtime_engine: str = Field(min_length=1)
    runtime_mode: EmbeddingRuntimeMode
    engine_revision_observed: str = UNKNOWN_REVISION
    status: EmbeddingRunStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None
    produced_embedding_bundle_id: str | None = None
    created_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        """Return whether the run reached a state the executor never leaves."""

        return self.status in {"completed", "failed", "cancelled", "blocked"}


class EmbeddingBundleChunk(StrictModel):
    """Mapping between one child chunk and its slot in the vector artifact."""

    embedding_bundle_id: str = Field(min_length=1)
    child_chunk_id: str = Field(min_length=1)
    parent_chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    vector_offset: int = Field(ge=0)
    vector_length: int = Field(gt=0)
    vector_checksum: str | None = None
    content_hash: str = Field(min_length=1)
    chunk_ordinal: int = Field(ge=0)


class EmbeddingBundle(StrictModel):
    """Sealed, immutable set of document vectors for one chunk bundle.

    ``project_id`` is nullable so legacy rows (``project_id IS NULL``) keep their
    behaviour, while platform bundles carry the owning project. It is **not** part
    of ``deterministic_id`` (the legacy id is preserved by ADR-007); the physical
    platform identity is enforced by the partial index
    ``uq_embedding_bundles_physical_identity`` at the database level.
    """

    embedding_bundle_id: str = Field(min_length=1)
    project_id: str | None = None
    source_chunk_bundle_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    normalization: Normalization
    distance_metric: DistanceMetric
    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_version: str = Field(min_length=1)
    semantic_config: dict[str, object] = Field(default_factory=dict)
    bundle_schema_version: str = BUNDLE_SCHEMA_VERSION
    source_content_fingerprint: str = Field(min_length=1)
    vector_artifact_relpath: str | None = None
    chunk_map_relpath: str | None = None
    vector_dtype: str | None = None
    vector_shape: str | None = None
    vector_count: int = Field(default=0, ge=0)
    checksums: dict[str, str] = Field(default_factory=dict)
    status: EmbeddingBundleStatus
    validation_status: BundleValidationStatus = "compatibility_not_proven"
    readiness_status: BundleReadinessStatus = "pending"
    created_at: datetime | None = None
    sealed_at: datetime | None = None

    @property
    def is_sealed(self) -> bool:
        """Return whether the bundle satisfies the sealed persistence contract."""

        return self.status == "sealed" and self.validation_status == "passed"

    @staticmethod
    def deterministic_id(
        *,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
        corpus_version: str,
        source_content_fingerprint: str,
        bundle_schema_version: str = BUNDLE_SCHEMA_VERSION,
    ) -> str:
        """Return the deterministic id implied by the persistence identity tuple."""

        digest = sha256(
            canonical_json(
                [
                    source_chunk_bundle_id,
                    embedding_profile_id,
                    configuration_fingerprint,
                    corpus_version,
                    source_content_fingerprint,
                    bundle_schema_version,
                ]
            ).encode("utf-8")
        ).hexdigest()
        return f"embedding-bundle-{digest}"


class ValidationCheck(StrictModel):
    """One named assertion evaluated while validating a bundle."""

    name: str = Field(min_length=1)
    passed: bool
    detail: str = ""


class EmbeddingBundleValidation(StrictModel):
    """Result of validating a sealed bundle against its source and profile."""

    embedding_bundle_id: str = Field(min_length=1)
    status: ReadinessCheckStatus
    validator_version: str = VALIDATOR_VERSION
    checks: list[ValidationCheck] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return whether every check passed."""

        return self.status == "passed"

    def failures(self) -> list[ValidationCheck]:
        """Return the failing checks, in evaluation order."""

        return [check for check in self.checks if not check.passed]


class EmbeddingIndexingReadiness(StrictModel):
    """Whether a validated bundle may be handed to Indexing."""

    embedding_bundle_id: str = Field(min_length=1)
    indexing_target_id: str | None = None
    status: BundleReadinessStatus
    blocking_reasons: list[str] = Field(default_factory=list)


class ChunkBundleRef(StrictModel):
    """Durable identity of one registered chunk bundle.

    ``project_id`` is nullable so legacy rows (``project_id IS NULL``) keep their
    current behaviour while platform-owned rows carry their owning project for the
    composite-FK isolation introduced in Fase 4 (ADR-007 §1).
    """

    chunk_bundle_id: str = Field(min_length=1)
    project_id: str | None = None
    bundle_fingerprint: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    profile_fingerprint: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    artifact_relpath: str = Field(min_length=1)
    source_relpath: str | None = None
    normalized_relpath: str | None = None
    source_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parent_count: int = Field(ge=0)
    child_count: int = Field(ge=0)
    status: CompatibilityStatus


class ReadinessCheck(StrictModel):
    """One durable ``readiness_checks`` row."""

    check_id: str = Field(min_length=1)
    check_kind: ReadinessCheckKind
    subject_id: str = Field(min_length=1)
    embedding_profile_id: str | None = None
    indexing_target_id: str | None = None
    status: ReadinessCheckStatus
    validator_version: str = VALIDATOR_VERSION
    report: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None

    @staticmethod
    def deterministic_id(
        *,
        check_kind: ReadinessCheckKind,
        subject_id: str,
        report: Mapping[str, object],
    ) -> str:
        """Return a content-addressed check id so replays stay idempotent."""

        digest = sha256(
            canonical_json([check_kind, subject_id, dict(report)]).encode("utf-8")
        ).hexdigest()
        return f"check-{digest}"
