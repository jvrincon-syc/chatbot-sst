"""Activation and rollback of indexed bundles.

Indexing, validating and activating are three separate operations. A finished
run never activates itself: ``ActivateIndexedBundleUseCase`` re-proves every
precondition, records a readiness check and only then flips the vector rows and
the owning retrieval profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from core.logging.observability import EventStatus, ObservabilityDomain
from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    EmbeddingBundleRepository,
    EmbeddingProfileRepository,
    ReadinessCheckRepository,
)
from embedding.domain.models import ReadinessCheck, ValidationCheck
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from indexing.application.bundle_first.ports import (
    BundleVectorWriter,
    IndexingRunRepository,
    IndexingTargetRepository,
    TransactionManager,
    resolved_profile_from_embedding_profile,
)
from indexing.domain.errors import IndexingActivationBlocked, IndexingTargetIncompatible
from retrieval.application.ports import RetrievalProfileRepository
from retrieval.domain.models import RetrievalProfile


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ActivationRequest:
    """One explicit activation of an indexed bundle for a consumer scope."""

    run_id: str
    consumer_scope_type: str
    consumer_scope_id: str
    lexical_fallback_policy: str = "allowed_when_vector_unavailable"


@dataclass(frozen=True)
class ActivationResult:
    """Outcome of one activation."""

    run_id: str
    embedding_bundle_id: str
    indexing_target_id: str
    retrieval_profile_id: str
    activated_rows: int
    checks: tuple[ValidationCheck, ...]


class ActivateIndexedBundleUseCase:
    """Validate, activate and publish one indexed bundle transactionally."""

    def __init__(
        self,
        *,
        runs: IndexingRunRepository,
        bundles: EmbeddingBundleRepository,
        profiles: EmbeddingProfileRepository,
        targets: IndexingTargetRepository,
        vectors: BundleVectorWriter,
        artifacts: FilesystemEmbeddingBundleArtifactStore,
        retrieval_profiles: RetrievalProfileRepository,
        readiness_checks: ReadinessCheckRepository,
        transactions: TransactionManager,
    ) -> None:
        self._runs = runs
        self._bundles = bundles
        self._profiles = profiles
        self._targets = targets
        self._vectors = vectors
        self._artifacts = artifacts
        self._retrieval_profiles = retrieval_profiles
        self._readiness_checks = readiness_checks
        self._transactions = transactions

    def execute(self, request: ActivationRequest) -> ActivationResult:
        """Activate one indexed bundle.

        Raises:
            IndexingActivationBlocked: When any precondition fails.
            IndexingTargetIncompatible: When the target is missing or wrong.
        """

        run = self._runs.get(request.run_id)
        bundle = self._bundles.get(str(run.embedding_bundle_id))
        profile = self._profiles.get(bundle.embedding_profile_id)
        target_id = str(run.indexing_target_id or profile.default_indexing_target_id or "")
        if not target_id:
            raise IndexingTargetIncompatible("indexing run has no resolved target")
        try:
            target = self._targets.get(target_id)
        except LookupError as error:
            raise IndexingTargetIncompatible(
                f"indexing target {target_id} does not exist"
            ) from error

        expected_rows = int(run.summary.get("vector_rows", 0) or 0)
        node_rows = int(run.summary.get("child_nodes", 0) or 0)
        checks = (
            ValidationCheck(
                name="embedding_bundle_sealed",
                passed=bundle.is_sealed,
                detail=bundle.status,
            ),
            ValidationCheck(
                name="indexing_run_completed",
                passed=run.status == "completed" and run.validation_status == "passed",
                detail=f"status={run.status} validation={run.validation_status}",
            ),
            ValidationCheck(
                name="indexing_target_compatible",
                passed=target.active
                and target.vector_table == profile.vector_table
                and target.accepts_metric(bundle.distance_metric),
                detail=f"ops={target.distance_ops}",
            ),
            ValidationCheck(
                name="node_and_vector_counts_match",
                passed=expected_rows == bundle.vector_count == node_rows,
                detail=f"vector_rows={expected_rows} bundle={bundle.vector_count} nodes={node_rows}",
            ),
            ValidationCheck(
                name="artifact_checksums_match",
                passed=self._artifacts.verify_checksums(
                    embedding_bundle_id=bundle.embedding_bundle_id,
                    expected={
                        name: digest
                        for name, digest in bundle.checksums.items()
                        if name != "manifest.json"
                    },
                ),
                detail="published artifacts differ from their recorded checksums",
            ),
        )
        report: dict[str, object] = {"checks": [check.model_dump() for check in checks]}
        passed = all(check.passed for check in checks)
        self._readiness_checks.record(
            ReadinessCheck(
                check_id=ReadinessCheck.deterministic_id(
                    check_kind="retrieval_readiness",
                    subject_id=bundle.embedding_bundle_id,
                    report=report,
                ),
                check_kind="retrieval_readiness",
                subject_id=bundle.embedding_bundle_id,
                embedding_profile_id=profile.profile_id,
                indexing_target_id=target.indexing_target_id,
                status="passed" if passed else "blocked",
                report=report,
            )
        )
        if not passed:
            raise IndexingActivationBlocked(
                "activation blocked: "
                + ",".join(check.name for check in checks if not check.passed)
            )

        resolved_profile = resolved_profile_from_embedding_profile(profile)
        retrieval_profile = RetrievalProfile.build(
            consumer_scope_type=request.consumer_scope_type,
            consumer_scope_id=request.consumer_scope_id,
            corpus_version=bundle.corpus_version,
            embedding_profile_id=profile.profile_id,
            indexing_target_id=target.indexing_target_id,
            lexical_fallback_policy=request.lexical_fallback_policy,
        )
        with self._transactions.transaction():
            self._vectors.activate_bundle(
                profile=resolved_profile,
                indexing_target_id=target.indexing_target_id,
                corpus_version=bundle.corpus_version,
                embedding_bundle_id=bundle.embedding_bundle_id,
            )
            self._bundles.set_readiness_status(
                embedding_bundle_id=bundle.embedding_bundle_id,
                readiness_status="ready",
            )
            self._runs.update(
                run.model_copy(
                    update={
                        "activation_status": "active",
                        "validation_status": "passed",
                    }
                )
            )
            stored_profile = self._retrieval_profiles.upsert(retrieval_profile)
            stored_profile = self._retrieval_profiles.activate(
                retrieval_profile_id=stored_profile.retrieval_profile_id,
                validated_at=_now(),
            )

        activated_rows = self._vectors.count_active_rows(
            profile=resolved_profile,
            indexing_target_id=target.indexing_target_id,
            corpus_version=bundle.corpus_version,
            embedding_bundle_id=bundle.embedding_bundle_id,
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexed_bundle_activated",
            status=EventStatus.COMPLETED,
            message="Indexed bundle activated",
            run_id=run.run_id,
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="activate",
            metrics={"active_vector_rows": activated_rows},
            attributes={
                "indexing_run_id": run.run_id,
                "embedding_bundle_id": bundle.embedding_bundle_id,
                "indexing_target_id": target.indexing_target_id,
                "retrieval_profile_id": stored_profile.retrieval_profile_id,
            },
        )
        return ActivationResult(
            run_id=run.run_id,
            embedding_bundle_id=bundle.embedding_bundle_id,
            indexing_target_id=target.indexing_target_id,
            retrieval_profile_id=stored_profile.retrieval_profile_id,
            activated_rows=activated_rows,
            checks=checks,
        )


@dataclass(frozen=True)
class RollbackRequest:
    """Revert a lane to a bundle that was already validated before."""

    current_embedding_bundle_id: str
    previous_embedding_bundle_id: str
    consumer_scope_type: str
    consumer_scope_id: str


class RollbackIndexedBundleUseCase:
    """Reactivate a previously validated bundle without regenerating embeddings."""

    def __init__(
        self,
        *,
        bundles: EmbeddingBundleRepository,
        profiles: EmbeddingProfileRepository,
        targets: IndexingTargetRepository,
        vectors: BundleVectorWriter,
        retrieval_profiles: RetrievalProfileRepository,
        transactions: TransactionManager,
    ) -> None:
        self._bundles = bundles
        self._profiles = profiles
        self._targets = targets
        self._vectors = vectors
        self._retrieval_profiles = retrieval_profiles
        self._transactions = transactions

    def execute(self, request: RollbackRequest) -> ActivationResult:
        """Roll one lane back to a validated bundle.

        Raises:
            IndexingActivationBlocked: When the previous bundle is not validated.
        """

        current = self._bundles.get(request.current_embedding_bundle_id)
        previous = self._bundles.get(request.previous_embedding_bundle_id)
        if not previous.is_sealed:
            raise IndexingActivationBlocked(
                "the previous embedding bundle was never validated"
            )
        if previous.embedding_profile_id != current.embedding_profile_id:
            raise IndexingActivationBlocked(
                "cannot roll back across different embedding profiles"
            )
        if previous.corpus_version != current.corpus_version:
            raise IndexingActivationBlocked(
                "cannot roll back across different corpus versions"
            )

        profile = self._profiles.get(previous.embedding_profile_id)
        target_id = str(profile.default_indexing_target_id or "")
        if not target_id:
            raise IndexingTargetIncompatible("profile has no default indexing target")
        target = self._targets.get(target_id)
        resolved_profile = resolved_profile_from_embedding_profile(profile)

        retrieval_profile = RetrievalProfile.build(
            consumer_scope_type=request.consumer_scope_type,
            consumer_scope_id=request.consumer_scope_id,
            corpus_version=previous.corpus_version,
            embedding_profile_id=profile.profile_id,
            indexing_target_id=target.indexing_target_id,
        )
        with self._transactions.transaction():
            self._vectors.rollback_to_bundle(
                profile=resolved_profile,
                indexing_target_id=target.indexing_target_id,
                corpus_version=previous.corpus_version,
                current_embedding_bundle_id=current.embedding_bundle_id,
                previous_embedding_bundle_id=previous.embedding_bundle_id,
            )
            self._bundles.set_readiness_status(
                embedding_bundle_id=current.embedding_bundle_id,
                readiness_status="blocked",
            )
            self._bundles.set_readiness_status(
                embedding_bundle_id=previous.embedding_bundle_id,
                readiness_status="ready",
            )
            stored_profile = self._retrieval_profiles.upsert(retrieval_profile)
            stored_profile = self._retrieval_profiles.activate(
                retrieval_profile_id=stored_profile.retrieval_profile_id,
                validated_at=_now(),
            )

        activated_rows = self._vectors.count_active_rows(
            profile=resolved_profile,
            indexing_target_id=target.indexing_target_id,
            corpus_version=previous.corpus_version,
            embedding_bundle_id=previous.embedding_bundle_id,
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexed_bundle_rolled_back",
            status=EventStatus.COMPLETED,
            message="Indexed bundle rolled back",
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="rollback",
            metrics={"active_vector_rows": activated_rows},
            attributes={
                "embedding_bundle_id": previous.embedding_bundle_id,
                "superseded_embedding_bundle_id": current.embedding_bundle_id,
                "indexing_target_id": target.indexing_target_id,
                "retrieval_profile_id": stored_profile.retrieval_profile_id,
            },
        )
        return ActivationResult(
            run_id="",
            embedding_bundle_id=previous.embedding_bundle_id,
            indexing_target_id=target.indexing_target_id,
            retrieval_profile_id=stored_profile.retrieval_profile_id,
            activated_rows=activated_rows,
            checks=(),
        )
