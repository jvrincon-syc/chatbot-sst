"""Explicit verification and promotion of durable embedding profiles.

Legacy profiles were left ``compatibility_not_proven`` with both enablement
flags false by ``20260805_14``. Nothing in this backend promotes them
implicitly: a profile becomes usable only after this use case observes a real
engine, proves every semantic field and persists a readiness check.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from core.logging.observability import EventStatus, ObservabilityDomain
from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    EmbeddingEngine,
    EmbeddingEngineRegistry,
    EmbeddingProfileRepository,
    ReadinessCheckRepository,
)
from embedding.domain.errors import (
    EmbeddingEngineNotFound,
    EmbeddingEngineUnavailable,
)
from embedding.domain.models import (
    UNKNOWN_REVISION,
    VALIDATOR_VERSION,
    EmbeddingProfile,
    ReadinessCheck,
    ValidationCheck,
)
from indexing.domain.bundle_first import IndexingTarget


logger = logging.getLogger(__name__)

#: ``readiness_checks.check_kind`` used for explicit profile verification.
#:
#: Added by ``20260805_16``. ``report_json.subject_kind`` is still written so the
#: documented logical rollback of that migration is lossless.
PROFILE_CHECK_KIND = "embedding_profile_verification"


class IndexingTargetReader:
    """Minimal read port over ``indexing_targets`` used during verification."""

    def get(self, indexing_target_id: str) -> IndexingTarget:
        """Return one target or raise ``LookupError``."""

        raise NotImplementedError


@dataclass(frozen=True)
class ProfileVerificationRequest:
    """One explicit request to verify and possibly enable a profile."""

    profile_id: str
    attested_model_revision: str | None = None
    enable_documents: bool = True
    enable_queries: bool = True


@dataclass(frozen=True)
class ProfileVerificationResult:
    """Outcome of one verification attempt."""

    profile_id: str
    passed: bool
    checks: tuple[ValidationCheck, ...]
    revision_source: str
    profile: EmbeddingProfile

    def failures(self) -> tuple[ValidationCheck, ...]:
        """Return the failing checks in evaluation order."""

        return tuple(check for check in self.checks if not check.passed)


class VerifyEmbeddingProfileCompatibilityUseCase:
    """Prove that a durable profile and its live engine describe one vector space."""

    def __init__(
        self,
        *,
        profiles: EmbeddingProfileRepository,
        registry: EmbeddingEngineRegistry,
        targets: IndexingTargetReader,
        readiness_checks: ReadinessCheckRepository,
    ) -> None:
        self._profiles = profiles
        self._registry = registry
        self._targets = targets
        self._readiness_checks = readiness_checks

    def execute(self, request: ProfileVerificationRequest) -> ProfileVerificationResult:
        """Run every semantic check and promote the profile only when all pass."""

        profile = self._profiles.get(request.profile_id)
        checks: list[ValidationCheck] = []

        engine: EmbeddingEngine | None = None
        try:
            engine = self._registry.resolve_document_engine(profile)
            checks.append(ValidationCheck(name="engine_resolved", passed=True))
        except (EmbeddingEngineNotFound, EmbeddingEngineUnavailable) as error:
            checks.append(
                ValidationCheck(name="engine_resolved", passed=False, detail=error.code)
            )

        revision_source = "unproven"
        if engine is not None:
            report = self._registry.validate_engine_compatibility(profile, engine)
            mismatched = {mismatch.field_name for mismatch in report.mismatches}
            for field_name in ("provider", "model", "dimension", "normalization"):
                failed = field_name in mismatched
                detail = next(
                    (
                        f"expected={mismatch.expected} observed={mismatch.observed}"
                        for mismatch in report.mismatches
                        if mismatch.field_name == field_name
                    ),
                    "",
                )
                checks.append(
                    ValidationCheck(
                        name=f"{field_name}_matches",
                        passed=not failed,
                        detail=detail,
                    )
                )
            revision_check, revision_source = self._check_revision(
                profile=profile,
                engine=engine,
                attested_model_revision=request.attested_model_revision,
            )
            checks.append(revision_check)

        checks.append(self._check_target_metric(profile))
        checks.append(self._check_fingerprint(profile))

        passed = all(check.passed for check in checks)
        report_payload: dict[str, object] = {
            "subject_kind": "embedding_profile",
            "revision_source": revision_source,
            "checks": [check.model_dump() for check in checks],
        }
        check_status = "passed" if passed else "failed"
        self._readiness_checks.record(
            ReadinessCheck(
                check_id=ReadinessCheck.deterministic_id(
                    check_kind=PROFILE_CHECK_KIND,
                    subject_id=profile.profile_id,
                    report=report_payload,
                ),
                check_kind=PROFILE_CHECK_KIND,
                subject_id=profile.profile_id,
                embedding_profile_id=profile.profile_id,
                indexing_target_id=profile.default_indexing_target_id,
                status=check_status,
                validator_version=VALIDATOR_VERSION,
                report=report_payload,
            )
        )

        if not passed:
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_profile_blocked",
                status=EventStatus.BLOCKED,
                message="Embedding profile compatibility was not proven",
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="verify_profile",
                attributes={
                    "embedding_profile_id": profile.profile_id,
                    "model": profile.model,
                    "model_revision": profile.model_revision,
                    "failed_checks": ",".join(
                        check.name for check in checks if not check.passed
                    ),
                },
            )
            return ProfileVerificationResult(
                profile_id=profile.profile_id,
                passed=False,
                checks=tuple(checks),
                revision_source=revision_source,
                profile=profile,
            )

        promoted = self._profiles.mark_verified(
            profile_id=profile.profile_id,
            configuration_fingerprint=profile.expected_fingerprint().value,
            model_revision=profile.model_revision,
            document_enabled=request.enable_documents,
            query_enabled=request.enable_queries,
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_profile_verified",
            status=EventStatus.COMPLETED,
            message="Embedding profile compatibility verified",
            profile_id=promoted.profile_id,
            provider=promoted.provider,
            capability="verify_profile",
            configuration_hash=promoted.configuration_fingerprint,
            attributes={
                "embedding_profile_id": promoted.profile_id,
                "model": promoted.model,
                "model_revision": promoted.model_revision,
                "revision_source": revision_source,
                "document_enabled": promoted.document_enabled,
                "query_enabled": promoted.query_enabled,
            },
        )
        return ProfileVerificationResult(
            profile_id=promoted.profile_id,
            passed=True,
            checks=tuple(checks),
            revision_source=revision_source,
            profile=promoted,
        )

    def _check_revision(
        self,
        *,
        profile: EmbeddingProfile,
        engine: EmbeddingEngine,
        attested_model_revision: str | None,
    ) -> tuple[ValidationCheck, str]:
        """Prove the profile revision against the engine or an explicit attestation."""

        if profile.model_revision == UNKNOWN_REVISION:
            return (
                ValidationCheck(
                    name="model_revision_matches",
                    passed=False,
                    detail="profile revision is unknown_revision and proves nothing",
                ),
                "unproven",
            )
        observed = engine.observe_revision()
        if observed != UNKNOWN_REVISION:
            return (
                ValidationCheck(
                    name="model_revision_matches",
                    passed=observed == profile.model_revision,
                    detail=f"expected={profile.model_revision} observed={observed}",
                ),
                "engine_observed",
            )
        if attested_model_revision is None:
            return (
                ValidationCheck(
                    name="model_revision_matches",
                    passed=False,
                    detail="engine exposes no revision and no operator attestation was given",
                ),
                "unproven",
            )
        return (
            ValidationCheck(
                name="model_revision_matches",
                passed=attested_model_revision == profile.model_revision,
                detail=f"expected={profile.model_revision} attested={attested_model_revision}",
            ),
            "operator_attestation",
        )

    def _check_target_metric(self, profile: EmbeddingProfile) -> ValidationCheck:
        """Prove the semantic metric matches the physical operator class."""

        if profile.default_indexing_target_id is None:
            return ValidationCheck(
                name="distance_metric_matches_target",
                passed=False,
                detail="profile has no default_indexing_target_id",
            )
        try:
            target = self._targets.get(profile.default_indexing_target_id)
        except LookupError:
            return ValidationCheck(
                name="distance_metric_matches_target",
                passed=False,
                detail="default indexing target does not exist",
            )
        matches = target.accepts_metric(profile.distance_metric) and (
            target.vector_table == profile.vector_table
        )
        return ValidationCheck(
            name="distance_metric_matches_target",
            passed=matches,
            detail=f"metric={profile.distance_metric} ops={target.distance_ops}",
        )

    def _check_fingerprint(self, profile: EmbeddingProfile) -> ValidationCheck:
        """Compare the recomputed semantic fingerprint with the stored one.

        A ``NULL`` fingerprint is not a failure: the column was added nullable by
        ``20260805_01`` and is sealed by this use case once every other check
        passed. A *different* stored fingerprint is always a failure.
        """

        recomputed = profile.expected_fingerprint().value
        if profile.configuration_fingerprint is None:
            return ValidationCheck(
                name="configuration_fingerprint_matches",
                passed=True,
                detail="fingerprint absent; sealed by this verification",
            )
        return ValidationCheck(
            name="configuration_fingerprint_matches",
            passed=profile.configuration_fingerprint == recomputed,
            detail="stored fingerprint differs from the recomputed semantic digest"
            if profile.configuration_fingerprint != recomputed
            else "",
        )
