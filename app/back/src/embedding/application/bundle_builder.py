"""Build, validate and gate sealed embedding bundles.

The builder is the only place that turns child chunks into vectors. It stages
artifacts, validates the result and seals the durable row in that order, because
``embedding_bundle_status_complete`` refuses a sealed row whose validation did
not pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import logging

from core.logging.observability import EventStatus, ObservabilityDomain
from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    EmbeddingBundleRepository,
    EmbeddingEngine,
    ReadinessCheckRepository,
)
from embedding.domain.errors import EmbeddingBundleInvalid
from embedding.domain.models import (
    BUNDLE_SCHEMA_VERSION,
    VALIDATOR_VERSION,
    ChunkBundleRef,
    EmbeddingBundle,
    EmbeddingBundleChunk,
    EmbeddingBundleValidation,
    EmbeddingIndexingReadiness,
    EmbeddingProfile,
    ReadinessCheck,
    ValidationCheck,
)
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    EMBEDDING_INPUT_TEMPLATE,
    ChunkBundleContent,
)
from indexing.domain.bundle_first import IndexingTarget


logger = logging.getLogger(__name__)

#: Default number of chunks handed to the engine per call.
DEFAULT_EMBEDDING_BATCH_SIZE = 32


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _vector_checksum(vector: Sequence[float]) -> str:
    """Digest one dense vector for per-row auditing."""

    payload = ",".join(f"{float(value):.6f}" for value in vector)
    return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BuiltBundle:
    """A sealed bundle plus the chunk map that was persisted with it."""

    bundle: EmbeddingBundle
    chunks: tuple[EmbeddingBundleChunk, ...]
    validation: EmbeddingBundleValidation


class EmbeddingBundleValidator:
    """Prove that a staged bundle matches its source, profile and artifacts."""

    def __init__(self, *, artifacts: FilesystemEmbeddingBundleArtifactStore) -> None:
        self._artifacts = artifacts

    def validate(
        self,
        *,
        bundle: EmbeddingBundle,
        profile: EmbeddingProfile,
        chunk_bundle: ChunkBundleRef | None,
        content: ChunkBundleContent,
        chunks: Sequence[EmbeddingBundleChunk],
        vectors: Sequence[Sequence[float]],
        verify_published_checksums: bool = False,
    ) -> EmbeddingBundleValidation:
        """Return the full validation report for one bundle."""

        children = content.children
        child_ids = [child.chunk_id for child in children]
        mapped_ids = [chunk.child_chunk_id for chunk in chunks]
        offsets = sorted(chunk.vector_offset for chunk in chunks)
        content_hash_by_id = {child.chunk_id: child.content_hash for child in children}

        checks = [
            ValidationCheck(
                name="source_chunk_bundle_registered",
                passed=chunk_bundle is not None,
                detail="" if chunk_bundle is not None else "chunk bundle is not registered",
            ),
            ValidationCheck(
                name="source_content_fingerprint_matches",
                passed=bundle.source_content_fingerprint == content.source_content_fingerprint,
                detail="source content drifted since the bundle was built"
                if bundle.source_content_fingerprint != content.source_content_fingerprint
                else "",
            ),
            ValidationCheck(
                name="profile_verified",
                passed=profile.is_verified,
                detail=profile.compatibility_status,
            ),
            ValidationCheck(
                name="configuration_homogeneous",
                passed=bundle.configuration_fingerprint == profile.expected_fingerprint().value,
                detail="bundle fingerprint differs from the recomputed profile digest"
                if bundle.configuration_fingerprint != profile.expected_fingerprint().value
                else "",
            ),
            ValidationCheck(
                name="engine_semantics_match_profile",
                passed=(
                    bundle.provider == profile.provider
                    and bundle.model == profile.model
                    and bundle.model_revision == profile.model_revision
                    and bundle.dimension == profile.dimension
                    and bundle.normalization == profile.normalization
                    and bundle.distance_metric == profile.distance_metric
                ),
                detail="bundle semantics differ from the durable profile",
            ),
            ValidationCheck(
                name="child_chunk_count_matches",
                passed=len(chunks) == len(children),
                detail=f"mapped={len(chunks)} source={len(children)}",
            ),
            ValidationCheck(
                name="vector_count_matches",
                passed=len(vectors) == len(children) == bundle.vector_count,
                detail=f"vectors={len(vectors)} source={len(children)} recorded={bundle.vector_count}",
            ),
            ValidationCheck(
                name="dimension_matches",
                passed=all(len(vector) == profile.dimension for vector in vectors),
                detail=f"expected={profile.dimension}",
            ),
            ValidationCheck(
                name="no_duplicate_children",
                passed=len(set(mapped_ids)) == len(mapped_ids),
                detail="duplicate child_chunk_id in the chunk map",
            ),
            ValidationCheck(
                name="no_missing_children",
                passed=set(mapped_ids) == set(child_ids),
                detail="chunk map does not cover every source child chunk",
            ),
            ValidationCheck(
                name="mapping_complete",
                passed=offsets == list(range(len(children))),
                detail="vector offsets are not a dense zero-based range",
            ),
            ValidationCheck(
                name="content_hashes_match",
                passed=all(
                    content_hash_by_id.get(chunk.child_chunk_id) == chunk.content_hash
                    for chunk in chunks
                ),
                detail="a mapped content hash does not match the source chunk",
            ),
            ValidationCheck(
                name="checksums_present",
                passed=bool(bundle.checksums)
                and all(chunk.vector_checksum for chunk in chunks),
                detail="artifact or per-vector checksums are missing",
            ),
        ]

        if verify_published_checksums:
            checks.append(
                ValidationCheck(
                    name="published_checksums_match",
                    passed=self._artifacts.verify_checksums(
                        embedding_bundle_id=bundle.embedding_bundle_id,
                        expected=bundle.checksums,
                    ),
                    detail="published artifacts do not match their recorded checksums",
                )
            )

        passed = all(check.passed for check in checks)
        return EmbeddingBundleValidation(
            embedding_bundle_id=bundle.embedding_bundle_id,
            status="passed" if passed else "failed",
            validator_version=VALIDATOR_VERSION,
            checks=checks,
        )


class EmbeddingBundleBuilder:
    """Embed one chunk bundle and seal the resulting artifacts atomically."""

    def __init__(
        self,
        *,
        bundles: EmbeddingBundleRepository,
        artifacts: FilesystemEmbeddingBundleArtifactStore,
        validator: EmbeddingBundleValidator,
        readiness_checks: ReadinessCheckRepository,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    ) -> None:
        self._bundles = bundles
        self._artifacts = artifacts
        self._validator = validator
        self._readiness_checks = readiness_checks
        self._batch_size = max(1, batch_size)

    def build(
        self,
        *,
        profile: EmbeddingProfile,
        chunk_bundle: ChunkBundleRef,
        content: ChunkBundleContent,
        engine: EmbeddingEngine,
        engine_revision_observed: str,
    ) -> BuiltBundle:
        """Embed, stage, validate, promote and seal one bundle.

        Raises:
            EmbeddingBundleInvalid: When validation fails; artifacts stay unstaged.
        """

        if not content.children:
            raise EmbeddingBundleInvalid("chunk bundle has no child chunks to embed")

        fingerprint = profile.expected_fingerprint().value
        bundle_id = EmbeddingBundle.deterministic_id(
            source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
            embedding_profile_id=profile.profile_id,
            configuration_fingerprint=fingerprint,
            corpus_version=chunk_bundle.corpus_version,
            source_content_fingerprint=content.source_content_fingerprint,
        )
        existing = self._bundles.find_by_identity(
            source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
            embedding_profile_id=profile.profile_id,
            configuration_fingerprint=fingerprint,
            corpus_version=chunk_bundle.corpus_version,
            source_content_fingerprint=content.source_content_fingerprint,
            bundle_schema_version=BUNDLE_SCHEMA_VERSION,
        )
        if existing is not None and existing.is_sealed:
            return BuiltBundle(
                bundle=existing,
                chunks=tuple(self._bundles.list_chunks(existing.embedding_bundle_id)),
                validation=EmbeddingBundleValidation(
                    embedding_bundle_id=existing.embedding_bundle_id,
                    status="passed",
                    checks=[ValidationCheck(name="already_sealed", passed=True)],
                ),
            )

        vectors = self._embed_children(content=content, engine=engine, profile=profile)
        chunks = tuple(
            EmbeddingBundleChunk(
                embedding_bundle_id=bundle_id,
                child_chunk_id=child.chunk_id,
                parent_chunk_id=child.parent_id,
                document_id=child.document_id,
                vector_offset=offset,
                vector_length=len(vectors[offset]),
                vector_checksum=_vector_checksum(vectors[offset]),
                content_hash=child.content_hash,
                chunk_ordinal=child.ordinal,
            )
            for offset, child in enumerate(content.children)
        )

        self._artifacts.discard_staging(embedding_bundle_id=bundle_id)
        refs = self._artifacts.stage(
            embedding_bundle_id=bundle_id,
            manifest={
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "source_chunk_bundle_id": chunk_bundle.chunk_bundle_id,
                "embedding_profile_id": profile.profile_id,
                "provider": profile.provider,
                "model": profile.model,
                "model_revision": profile.model_revision,
                "dimension": profile.dimension,
                "normalization": profile.normalization,
                "distance_metric": profile.distance_metric,
                "configuration_fingerprint": fingerprint,
                "corpus_version": chunk_bundle.corpus_version,
                "source_content_fingerprint": content.source_content_fingerprint,
                "embedding_input_template": EMBEDDING_INPUT_TEMPLATE,
                "engine_revision_observed": engine_revision_observed,
            },
            vectors=vectors,
            chunk_map=[
                {
                    "child_chunk_id": chunk.child_chunk_id,
                    "parent_chunk_id": chunk.parent_chunk_id,
                    "document_id": chunk.document_id,
                    "vector_offset": chunk.vector_offset,
                    "vector_length": chunk.vector_length,
                    "vector_checksum": chunk.vector_checksum,
                    "content_hash": chunk.content_hash,
                    "chunk_ordinal": chunk.chunk_ordinal,
                }
                for chunk in chunks
            ],
        )

        pending = EmbeddingBundle(
            embedding_bundle_id=bundle_id,
            source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
            embedding_profile_id=profile.profile_id,
            provider=profile.provider,
            model=profile.model,
            model_revision=profile.model_revision,
            dimension=profile.dimension,
            normalization=profile.normalization,
            distance_metric=profile.distance_metric,
            configuration_fingerprint=fingerprint,
            corpus_version=chunk_bundle.corpus_version,
            semantic_config=dict(profile.semantic_config),
            bundle_schema_version=BUNDLE_SCHEMA_VERSION,
            source_content_fingerprint=content.source_content_fingerprint,
            vector_artifact_relpath=refs.vector_artifact_relpath,
            chunk_map_relpath=refs.chunk_map_relpath,
            vector_dtype=refs.dtype,
            vector_shape=refs.shape,
            vector_count=len(vectors),
            checksums=dict(refs.checksums),
            status="pending",
            validation_status="pending",
            readiness_status="pending",
            created_at=_now(),
        )
        self._bundles.upsert(pending)
        self._bundles.replace_chunks(embedding_bundle_id=bundle_id, chunks=chunks)

        validation = self._validator.validate(
            bundle=pending,
            profile=profile,
            chunk_bundle=chunk_bundle,
            content=content,
            chunks=chunks,
            vectors=vectors,
        )
        self._record_validation(bundle=pending, profile=profile, validation=validation)
        if not validation.passed:
            self._artifacts.discard_staging(embedding_bundle_id=bundle_id)
            self._bundles.upsert(
                pending.model_copy(
                    update={"status": "failed", "validation_status": "failed"}
                )
            )
            raise EmbeddingBundleInvalid(
                "embedding bundle failed validation: "
                + ",".join(check.name for check in validation.failures())
            )

        self._artifacts.promote(embedding_bundle_id=bundle_id)
        sealed = self._bundles.seal(
            pending.model_copy(
                update={
                    "status": "sealed",
                    "validation_status": "passed",
                    "readiness_status": "pending",
                    "sealed_at": _now(),
                }
            )
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_bundle_sealed",
            status=EventStatus.COMPLETED,
            message="Embedding bundle sealed",
            document_id=content.document_id,
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="embed",
            configuration_hash=fingerprint,
            metrics={"vector_count": len(vectors)},
            attributes={
                "embedding_bundle_id": bundle_id,
                "source_chunk_bundle_id": chunk_bundle.chunk_bundle_id,
                "embedding_profile_id": profile.profile_id,
                "model": profile.model,
                "model_revision": profile.model_revision,
            },
        )
        return BuiltBundle(bundle=sealed, chunks=chunks, validation=validation)

    def _embed_children(
        self,
        *,
        content: ChunkBundleContent,
        engine: EmbeddingEngine,
        profile: EmbeddingProfile,
    ) -> list[list[float]]:
        texts = [child.embedding_input for child in content.children]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            batch_vectors = engine.embed_documents(batch)
            if len(batch_vectors) != len(batch):
                raise EmbeddingBundleInvalid(
                    "embedding engine returned a different number of vectors"
                )
            vectors.extend(batch_vectors)
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_batch_completed",
                status=EventStatus.COMPLETED,
                message="Embedding batch completed",
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                metrics={"batch_size": len(batch), "embedded_total": len(vectors)},
                attributes={"embedding_profile_id": profile.profile_id},
            )
        if any(len(vector) != profile.dimension for vector in vectors):
            raise EmbeddingBundleInvalid(
                "embedding engine returned a vector with the wrong dimension"
            )
        return vectors

    def _record_validation(
        self,
        *,
        bundle: EmbeddingBundle,
        profile: EmbeddingProfile,
        validation: EmbeddingBundleValidation,
    ) -> None:
        report: dict[str, object] = {
            "checks": [check.model_dump() for check in validation.checks],
        }
        self._readiness_checks.record(
            ReadinessCheck(
                check_id=ReadinessCheck.deterministic_id(
                    check_kind="embedding_bundle_validation",
                    subject_id=bundle.embedding_bundle_id,
                    report=report,
                ),
                check_kind="embedding_bundle_validation",
                subject_id=bundle.embedding_bundle_id,
                embedding_profile_id=profile.profile_id,
                indexing_target_id=profile.default_indexing_target_id,
                status=validation.status,
                report=report,
            )
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_bundle_validated",
            status=EventStatus.COMPLETED if validation.passed else EventStatus.FAILED,
            message="Embedding bundle validated",
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="embed",
            attributes={
                "embedding_bundle_id": bundle.embedding_bundle_id,
                "embedding_profile_id": profile.profile_id,
                "validation_status": validation.status,
            },
        )


class EmbeddingIndexingReadinessEvaluator:
    """Decide whether a sealed bundle may be handed to Indexing."""

    def __init__(self, *, targets: object) -> None:
        self._targets = targets

    def evaluate(
        self,
        *,
        bundle: EmbeddingBundle,
        profile: EmbeddingProfile,
    ) -> EmbeddingIndexingReadiness:
        """Return the readiness verdict and every blocking reason."""

        reasons: list[str] = []
        if not bundle.is_sealed:
            reasons.append("EMBEDDING_BUNDLE_INVALID")
        if not profile.is_verified:
            reasons.append("EMBEDDING_PROFILE_COMPATIBILITY_NOT_PROVEN")
        if not profile.document_enabled:
            reasons.append("EMBEDDING_PROFILE_DOCUMENTS_DISABLED")
        if bundle.configuration_fingerprint != profile.expected_fingerprint().value:
            reasons.append("EMBEDDING_ENGINE_SEMANTIC_MISMATCH")

        target: IndexingTarget | None = None
        target_id = profile.default_indexing_target_id
        if target_id is None:
            reasons.append("INDEXING_TARGET_INCOMPATIBLE")
        else:
            try:
                target = self._targets.get(target_id)
            except LookupError:
                target = None
            if target is None or not target.active:
                reasons.append("INDEXING_TARGET_INCOMPATIBLE")
            elif not target.accepts_metric(bundle.distance_metric):
                reasons.append("INDEXING_TARGET_INCOMPATIBLE")
            elif target.vector_table != profile.vector_table:
                reasons.append("INDEXING_TARGET_INCOMPATIBLE")

        return EmbeddingIndexingReadiness(
            embedding_bundle_id=bundle.embedding_bundle_id,
            indexing_target_id=target_id,
            status="ready" if not reasons else "blocked",
            blocking_reasons=reasons,
        )
