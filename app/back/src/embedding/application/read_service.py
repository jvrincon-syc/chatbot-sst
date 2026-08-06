"""Read-side application service backing the Embedding API.

Routes stay thin: they validate input, call one method here and translate domain
errors into the shared envelope. Nothing in this module returns a vector.
"""

from __future__ import annotations

from datetime import datetime

from embedding.application.bundle_builder import EmbeddingIndexingReadinessEvaluator
from embedding.application.ports import (
    ChunkBundleRepository,
    EmbeddingBundleRepository,
    EmbeddingEngineRegistry,
    EmbeddingProfileRepository,
    EmbeddingRunRepository,
    ReadinessCheckRepository,
)
from embedding.domain.models import (
    ChunkBundleRef,
    EmbeddingBundle,
    EmbeddingProfile,
    EmbeddingRun,
)


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


class EmbeddingReadService:
    """Expose durable embedding state as plain, sanitized payloads."""

    def __init__(
        self,
        *,
        profiles: EmbeddingProfileRepository,
        chunk_bundles: ChunkBundleRepository,
        runs: EmbeddingRunRepository,
        bundles: EmbeddingBundleRepository,
        readiness_checks: ReadinessCheckRepository,
        registry: EmbeddingEngineRegistry,
        readiness_evaluator: EmbeddingIndexingReadinessEvaluator,
    ) -> None:
        self._profiles = profiles
        self._chunk_bundles = chunk_bundles
        self._runs = runs
        self._bundles = bundles
        self._readiness_checks = readiness_checks
        self._registry = registry
        self._readiness_evaluator = readiness_evaluator

    def list_profiles(self) -> list[dict[str, object]]:
        """Return every profile, blocked ones included."""

        return [_profile_payload(profile) for profile in self._profiles.list_profiles()]

    def list_runtime(self) -> list[dict[str, object]]:
        """Return engine availability per profile without raising."""

        return [
            self._registry.get_runtime_status(profile).model_dump()
            for profile in self._profiles.list_profiles()
        ]

    def list_chunk_bundles(self) -> list[dict[str, object]]:
        """Return every registered chunk bundle."""

        return [_chunk_bundle_payload(bundle) for bundle in self._chunk_bundles.list_bundles()]

    def get_chunk_bundle_summary(self, chunk_bundle_id: str) -> dict[str, object]:
        """Return one chunk bundle plus the embedding bundles built from it."""

        chunk_bundle = self._chunk_bundles.get(chunk_bundle_id)
        produced = [
            run.produced_embedding_bundle_id
            for run in self._runs.list_runs()
            if run.source_chunk_bundle_id == chunk_bundle_id
            and run.produced_embedding_bundle_id is not None
        ]
        return {
            **_chunk_bundle_payload(chunk_bundle),
            "profile_fingerprint": chunk_bundle.profile_fingerprint,
            "embedding_bundle_ids": sorted(set(produced)),
        }

    def list_runs(self) -> list[dict[str, object]]:
        """Return every run, newest first."""

        return [_run_payload(run) for run in self._runs.list_runs()]

    def get_run(self, embedding_run_id: str) -> dict[str, object]:
        """Return one run."""

        return _run_payload(self._runs.get(embedding_run_id))

    def get_bundle(self, embedding_bundle_id: str) -> dict[str, object]:
        """Return one bundle."""

        return _bundle_payload(self._bundles.get(embedding_bundle_id))

    def list_bundle_chunks(self, embedding_bundle_id: str) -> list[dict[str, object]]:
        """Return the durable chunk map of one bundle."""

        self._bundles.get(embedding_bundle_id)
        return [
            chunk.model_dump(exclude={"embedding_bundle_id"})
            for chunk in self._bundles.list_chunks(embedding_bundle_id)
        ]

    def get_bundle_validation(self, embedding_bundle_id: str) -> dict[str, object]:
        """Return the persisted validation report of one bundle."""

        bundle = self._bundles.get(embedding_bundle_id)
        check = self._readiness_checks.latest(
            check_kind="embedding_bundle_validation",
            subject_id=embedding_bundle_id,
        )
        checks = list(check.report.get("checks", [])) if check is not None else []
        return {
            "embedding_bundle_id": embedding_bundle_id,
            "status": check.status if check is not None else bundle.validation_status,
            "validator_version": check.validator_version if check is not None else "unknown",
            "checks": checks,
        }

    def get_bundle_indexing_readiness(self, embedding_bundle_id: str) -> dict[str, object]:
        """Return whether the bundle may be handed to Indexing."""

        bundle = self._bundles.get(embedding_bundle_id)
        profile = self._profiles.get(bundle.embedding_profile_id)
        return self._readiness_evaluator.evaluate(bundle=bundle, profile=profile).model_dump()


def _profile_payload(profile: EmbeddingProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model": profile.model,
        "model_revision": profile.model_revision,
        "dimension": profile.dimension,
        "normalization": profile.normalization,
        "distance_metric": profile.distance_metric,
        "configuration_fingerprint": profile.configuration_fingerprint,
        "ingestion_origin": profile.ingestion_origin,
        "chunking_version": profile.chunking_version,
        "vector_table": profile.vector_table,
        "default_indexing_target_id": profile.default_indexing_target_id,
        "active": profile.active,
        "document_enabled": profile.document_enabled,
        "query_enabled": profile.query_enabled,
        "compatibility_status": profile.compatibility_status,
        "deprecated_at": _isoformat(profile.deprecated_at),
        "can_embed_documents": profile.can_embed_documents,
        "can_embed_queries": profile.can_embed_queries,
    }


def _chunk_bundle_payload(bundle: ChunkBundleRef) -> dict[str, object]:
    return {
        "chunk_bundle_id": bundle.chunk_bundle_id,
        "bundle_fingerprint": bundle.bundle_fingerprint,
        "profile_id": bundle.profile_id,
        "corpus_version": bundle.corpus_version,
        "source_document_id": bundle.source_document_id,
        "parent_count": bundle.parent_count,
        "child_count": bundle.child_count,
        "status": bundle.status,
    }


def _run_payload(run: EmbeddingRun) -> dict[str, object]:
    return {
        "embedding_run_id": run.embedding_run_id,
        "idempotency_key": run.idempotency_key,
        "request_fingerprint": run.request_fingerprint,
        "source_chunk_bundle_id": run.source_chunk_bundle_id,
        "embedding_profile_id": run.embedding_profile_id,
        "configuration_fingerprint": run.configuration_fingerprint,
        "runtime_engine": run.runtime_engine,
        "runtime_mode": run.runtime_mode,
        "engine_revision_observed": run.engine_revision_observed,
        "status": run.status,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "summary": dict(run.summary),
        "warnings": list(run.warnings),
        "error_summary": run.error_summary,
        "produced_embedding_bundle_id": run.produced_embedding_bundle_id,
        "links": {
            "self": f"/api/embedding/runs/{run.embedding_run_id}",
            **(
                {"bundle": f"/api/embedding/bundles/{run.produced_embedding_bundle_id}"}
                if run.produced_embedding_bundle_id
                else {}
            ),
        },
    }


def _bundle_payload(bundle: EmbeddingBundle) -> dict[str, object]:
    return {
        "embedding_bundle_id": bundle.embedding_bundle_id,
        "source_chunk_bundle_id": bundle.source_chunk_bundle_id,
        "embedding_profile_id": bundle.embedding_profile_id,
        "provider": bundle.provider,
        "model": bundle.model,
        "model_revision": bundle.model_revision,
        "dimension": bundle.dimension,
        "normalization": bundle.normalization,
        "distance_metric": bundle.distance_metric,
        "configuration_fingerprint": bundle.configuration_fingerprint,
        "corpus_version": bundle.corpus_version,
        "bundle_schema_version": bundle.bundle_schema_version,
        "source_content_fingerprint": bundle.source_content_fingerprint,
        "vector_dtype": bundle.vector_dtype,
        "vector_shape": bundle.vector_shape,
        "vector_count": bundle.vector_count,
        "checksums": dict(bundle.checksums),
        "status": bundle.status,
        "validation_status": bundle.validation_status,
        "readiness_status": bundle.readiness_status,
        "sealed_at": _isoformat(bundle.sealed_at),
        "links": {
            "self": f"/api/embedding/bundles/{bundle.embedding_bundle_id}",
            "chunks": f"/api/embedding/bundles/{bundle.embedding_bundle_id}/chunks",
            "validation": f"/api/embedding/bundles/{bundle.embedding_bundle_id}/validation",
            "indexing_readiness": (
                f"/api/embedding/bundles/{bundle.embedding_bundle_id}/indexing-readiness"
            ),
        },
    }
