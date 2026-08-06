"""Read-side application service backing the bundle-first Indexing API."""

from __future__ import annotations

from datetime import datetime

from embedding.application.ports import (
    EmbeddingBundleRepository,
    EmbeddingProfileRepository,
)
from indexing.application.bundle_first.ports import (
    BundleVectorWriter,
    IndexingRunDocumentRepository,
    IndexingRunRepository,
    IndexingTargetRepository,
    resolved_profile_from_embedding_profile,
)
from indexing.domain.bundle_first import (
    IndexingRetrievalReadiness,
    IndexingRun,
    IndexingRunDocument,
    IndexingTarget,
)


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


class IndexingReadService:
    """Expose durable indexing state as plain, sanitized payloads."""

    def __init__(
        self,
        *,
        runs: IndexingRunRepository,
        run_documents: IndexingRunDocumentRepository,
        targets: IndexingTargetRepository,
        profiles: EmbeddingProfileRepository,
        bundles: EmbeddingBundleRepository,
        vectors: BundleVectorWriter,
        bundle_first_enabled: bool,
    ) -> None:
        self._runs = runs
        self._run_documents = run_documents
        self._targets = targets
        self._profiles = profiles
        self._bundles = bundles
        self._vectors = vectors
        self._bundle_first_enabled = bundle_first_enabled

    def overview(self) -> dict[str, object]:
        """Return the aggregate state of the bundle-first indexing surface."""

        targets = self._targets.list_targets()
        profiles = self._profiles.list_profiles()
        runs = self._runs.list_runs()
        return {
            "targets": len(targets),
            "active_targets": sum(1 for target in targets if target.active),
            "profiles": len(profiles),
            "verified_profiles": sum(1 for profile in profiles if profile.is_verified),
            "sealed_bundles": sum(
                1
                for run in runs
                if run.embedding_bundle_id and run.validation_status == "passed"
            ),
            "runs": len(runs),
            "completed_runs": sum(1 for run in runs if run.status == "completed"),
            "active_runs": sum(1 for run in runs if run.activation_status == "active"),
            "bundle_first_enabled": self._bundle_first_enabled,
        }

    def list_targets(self) -> list[dict[str, object]]:
        """Return every registered target."""

        return [_target_payload(target) for target in self._targets.list_targets()]

    def list_runs(self) -> list[dict[str, object]]:
        """Return every run, newest first."""

        return [_run_payload(run) for run in self._runs.list_runs()]

    def get_run(self, run_id: str) -> dict[str, object]:
        """Return one run."""

        return _run_payload(self._runs.get(run_id))

    def list_run_documents(self, run_id: str) -> list[dict[str, object]]:
        """Return the per-document outcome of one run."""

        self._runs.get(run_id)
        return [
            _run_document_payload(document)
            for document in self._run_documents.list_for_run(run_id)
        ]

    def list_run_errors(self, run_id: str) -> list[dict[str, object]]:
        """Return only the sanitized failures of one run."""

        run = self._runs.get(run_id)
        errors = [
            {
                "document_id": document.document_id,
                "status": document.status,
                "error_code": document.error_code,
                "internal_error_id": document.internal_error_id,
            }
            for document in self._run_documents.list_for_run(run_id)
            if document.status in {"failed", "skipped"}
        ]
        run_error_code = run.summary.get("error_code")
        if not errors and run.status == "failed" and run_error_code:
            errors.append(
                {
                    "document_id": "",
                    "status": "failed",
                    "error_code": str(run_error_code),
                    "internal_error_id": None,
                }
            )
        return errors

    def get_retrieval_readiness(self, run_id: str) -> dict[str, object]:
        """Return whether the indexed run can serve retrieval traffic."""

        run = self._runs.get(run_id)
        reasons: list[str] = []
        active_rows = 0
        if run.status != "completed":
            reasons.append("INDEXING_RUN_NOT_COMPLETED")
        if run.activation_status != "active":
            reasons.append("INDEXING_BUNDLE_NOT_ACTIVATED")
        if run.embedding_bundle_id and run.indexing_target_id and run.corpus_version:
            bundle = self._bundles.get(run.embedding_bundle_id)
            profile = self._profiles.get(bundle.embedding_profile_id)
            active_rows = self._vectors.count_active_rows(
                profile=resolved_profile_from_embedding_profile(profile),
                indexing_target_id=run.indexing_target_id,
                corpus_version=run.corpus_version,
                embedding_bundle_id=run.embedding_bundle_id,
            )
            if active_rows == 0:
                reasons.append("NO_ACTIVE_VECTOR_ROWS")
        else:
            reasons.append("INDEXING_TARGET_INCOMPATIBLE")
        return IndexingRetrievalReadiness(
            run_id=run_id,
            embedding_bundle_id=run.embedding_bundle_id,
            indexing_target_id=run.indexing_target_id,
            corpus_version=run.corpus_version,
            ready=not reasons,
            active_vector_rows=active_rows,
            blocking_reasons=sorted(set(reasons)),
        ).model_dump()


def _target_payload(target: IndexingTarget) -> dict[str, object]:
    return {
        "indexing_target_id": target.indexing_target_id,
        "postgres_schema": target.postgres_schema,
        "vector_table": target.vector_table,
        "distance_ops": target.distance_ops,
        "storage_schema_version": target.storage_schema_version,
        "active": target.active,
        "deprecated_at": _isoformat(target.deprecated_at),
    }


def _run_payload(run: IndexingRun) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "profile_id": run.profile_id,
        "status": run.status,
        "embedding_bundle_id": run.embedding_bundle_id,
        "embedding_profile_id": run.embedding_profile_id,
        "indexing_target_id": run.indexing_target_id,
        "corpus_version": run.corpus_version,
        "idempotency_key": run.idempotency_key,
        "request_fingerprint": run.request_fingerprint,
        "validation_status": run.validation_status,
        "activation_status": run.activation_status,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "summary": dict(run.summary),
        "warnings": list(run.warnings),
        "links": {
            "self": f"/api/indexing/runs/{run.run_id}",
            "documents": f"/api/indexing/runs/{run.run_id}/documents",
            "errors": f"/api/indexing/runs/{run.run_id}/errors",
            "retrieval_readiness": f"/api/indexing/runs/{run.run_id}/retrieval-readiness",
        },
    }


def _run_document_payload(document: IndexingRunDocument) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "source_relpath": document.source_relpath,
        "status": document.status,
        "eligibility_status": document.eligibility_status,
        "eligibility_reason": document.eligibility_reason,
        "source_chunk_bundle_id": document.source_chunk_bundle_id,
        "embedding_bundle_id": document.embedding_bundle_id,
        "parent_count": document.parent_count,
        "child_count": document.child_count,
        "vector_count": document.vector_count,
        "started_at": _isoformat(document.started_at),
        "committed_at": _isoformat(document.committed_at),
        "error_code": document.error_code,
        "internal_error_id": document.internal_error_id,
    }
