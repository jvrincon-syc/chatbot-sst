"""In-memory repositories for tests, dry-run wiring and local development.

They implement exactly the same observable contract as the PostgreSQL adapters,
including the uniqueness and enablement invariants enforced by the SQL
constraints, so a contract test can run against either implementation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
import threading

from embedding.domain.errors import (
    ChunkBundleNotFound,
    EmbeddingBundleInvalid,
    EmbeddingBundleNotFound,
    EmbeddingProfileNotFound,
    EmbeddingRunNotFound,
)
from embedding.domain.models import (
    ChunkBundleRef,
    EmbeddingBundle,
    EmbeddingBundleChunk,
    EmbeddingProfile,
    EmbeddingRun,
    ReadinessCheck,
)
from indexing.domain.bundle_first import IndexingTarget


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryIndexingTargetRepository:
    """Deterministic ``indexing_targets`` double."""

    def __init__(self, targets: Iterable[IndexingTarget] = ()) -> None:
        self._targets = {target.indexing_target_id: target for target in targets}

    def get(self, indexing_target_id: str) -> IndexingTarget:
        """Return one target or raise ``LookupError``."""

        try:
            return self._targets[indexing_target_id]
        except KeyError as error:
            raise LookupError(f"indexing target not found: {indexing_target_id}") from error

    def list_targets(self) -> list[IndexingTarget]:
        """Return every registered target."""

        return list(self._targets.values())


class InMemoryEmbeddingProfileRepository:
    """Deterministic ``indexing_profiles`` double."""

    def __init__(self, profiles: Iterable[EmbeddingProfile] = ()) -> None:
        self._profiles = {profile.profile_id: profile for profile in profiles}

    def get(self, profile_id: str) -> EmbeddingProfile:
        """Return one profile or raise ``EmbeddingProfileNotFound``."""

        try:
            return self._profiles[profile_id]
        except KeyError as error:
            raise EmbeddingProfileNotFound(f"embedding profile not found: {profile_id}") from error

    def list_profiles(self) -> list[EmbeddingProfile]:
        """Return every registered profile, blocked ones included."""

        return list(self._profiles.values())

    def mark_verified(
        self,
        *,
        profile_id: str,
        configuration_fingerprint: str,
        model_revision: str,
        document_enabled: bool,
        query_enabled: bool,
    ) -> EmbeddingProfile:
        """Promote one profile, mirroring the SQL enablement constraint."""

        profile = self.get(profile_id)
        promoted = profile.model_copy(
            update={
                "compatibility_status": "verified",
                "configuration_fingerprint": configuration_fingerprint,
                "model_revision": model_revision,
                "document_enabled": document_enabled,
                "query_enabled": query_enabled,
            }
        )
        self._profiles[profile_id] = promoted
        return promoted


class InMemoryChunkBundleRepository:
    """Deterministic ``chunk_bundles`` double."""

    def __init__(self, bundles: Iterable[ChunkBundleRef] = ()) -> None:
        self._bundles = {bundle.chunk_bundle_id: bundle for bundle in bundles}

    def get(self, chunk_bundle_id: str) -> ChunkBundleRef:
        """Return one chunk bundle or raise ``ChunkBundleNotFound``."""

        try:
            return self._bundles[chunk_bundle_id]
        except KeyError as error:
            raise ChunkBundleNotFound(f"chunk bundle not found: {chunk_bundle_id}") from error

    def list_bundles(self) -> list[ChunkBundleRef]:
        """Return every registered chunk bundle."""

        return list(self._bundles.values())

    def ensure_registered(self, bundle: ChunkBundleRef) -> ChunkBundleRef:
        """Persist one bundle identity for later lookups."""

        self._bundles[bundle.chunk_bundle_id] = bundle
        return bundle


class InMemoryEmbeddingRunRepository:
    """Deterministic ``embedding_runs`` double with a transactional claim."""

    def __init__(self) -> None:
        self._runs: dict[str, EmbeddingRun] = {}
        self._by_key: dict[str, str] = {}
        self._lock = threading.Lock()

    def create(self, run: EmbeddingRun) -> EmbeddingRun:
        """Insert a run, honouring the ``(idempotency_key, request_fingerprint)`` key."""

        with self._lock:
            self._runs[run.embedding_run_id] = run
            self._by_key[run.idempotency_key] = run.embedding_run_id
        return run

    def get(self, embedding_run_id: str) -> EmbeddingRun:
        """Return one run or raise ``EmbeddingRunNotFound``."""

        with self._lock:
            run = self._runs.get(embedding_run_id)
        if run is None:
            raise EmbeddingRunNotFound(f"embedding run not found: {embedding_run_id}")
        return run

    def find_by_idempotency_key(self, idempotency_key: str) -> EmbeddingRun | None:
        """Return the run stored under one idempotency key."""

        with self._lock:
            run_id = self._by_key.get(idempotency_key)
            return self._runs.get(run_id) if run_id else None

    def list_runs(self) -> list[EmbeddingRun]:
        """Return every run, newest first."""

        with self._lock:
            runs = list(self._runs.values())
        return sorted(runs, key=lambda run: (run.created_at or _now()), reverse=True)

    def claim(self, embedding_run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once."""

        with self._lock:
            run = self._runs.get(embedding_run_id)
            if run is None or run.status != "pending":
                return False
            self._runs[embedding_run_id] = run.model_copy(
                update={"status": "running", "started_at": _now()}
            )
            return True

    def update(self, run: EmbeddingRun) -> EmbeddingRun:
        """Persist a durable state transition."""

        with self._lock:
            if run.embedding_run_id not in self._runs:
                raise EmbeddingRunNotFound(
                    f"embedding run not found: {run.embedding_run_id}"
                )
            self._runs[run.embedding_run_id] = run
        return run

    def reconcile_interrupted(self) -> list[str]:
        """Fail runs left ``running`` by a process that never finished."""

        reconciled: list[str] = []
        with self._lock:
            for run_id, run in list(self._runs.items()):
                if run.status == "running":
                    self._runs[run_id] = run.model_copy(
                        update={
                            "status": "failed",
                            "error_summary": "EMBEDDING_RUN_INTERRUPTED",
                            "completed_at": _now(),
                        }
                    )
                    reconciled.append(run_id)
        return reconciled


class InMemoryEmbeddingBundleRepository:
    """Deterministic ``embedding_bundles`` double with append-only sealing."""

    def __init__(self) -> None:
        self._bundles: dict[str, EmbeddingBundle] = {}
        self._chunks: dict[str, list[EmbeddingBundleChunk]] = {}

    def upsert(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Insert or update an unsealed bundle."""

        current = self._bundles.get(bundle.embedding_bundle_id)
        if current is not None and current.is_sealed:
            raise EmbeddingBundleInvalid("cannot modify a sealed embedding bundle")
        self._bundles[bundle.embedding_bundle_id] = bundle
        return bundle

    def seal(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Persist the sealed bundle, mirroring the SQL completeness constraint."""

        current = self._bundles.get(bundle.embedding_bundle_id)
        if current is not None and current.is_sealed:
            raise EmbeddingBundleInvalid("cannot re-seal an embedding bundle")
        if bundle.status == "sealed" and not (
            bundle.sealed_at is not None
            and bundle.vector_count > 0
            and bundle.vector_dtype
            and bundle.vector_shape
            and bundle.vector_artifact_relpath
            and bundle.chunk_map_relpath
            and bundle.validation_status == "passed"
        ):
            raise EmbeddingBundleInvalid("sealed bundle is incomplete")
        self._bundles[bundle.embedding_bundle_id] = bundle
        return bundle

    def get(self, embedding_bundle_id: str) -> EmbeddingBundle:
        """Return one bundle or raise ``EmbeddingBundleNotFound``."""

        bundle = self._bundles.get(embedding_bundle_id)
        if bundle is None:
            raise EmbeddingBundleNotFound(
                f"embedding bundle not found: {embedding_bundle_id}"
            )
        return bundle

    def find_by_identity(
        self,
        *,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
        corpus_version: str,
        source_content_fingerprint: str,
        bundle_schema_version: str,
    ) -> EmbeddingBundle | None:
        """Return an existing bundle for the deterministic identity tuple."""

        identity = (
            source_chunk_bundle_id,
            embedding_profile_id,
            configuration_fingerprint,
            corpus_version,
            source_content_fingerprint,
            bundle_schema_version,
        )
        for bundle in self._bundles.values():
            if (
                bundle.source_chunk_bundle_id,
                bundle.embedding_profile_id,
                bundle.configuration_fingerprint,
                bundle.corpus_version,
                bundle.source_content_fingerprint,
                bundle.bundle_schema_version,
            ) == identity:
                return bundle
        return None

    def replace_chunks(
        self,
        *,
        embedding_bundle_id: str,
        chunks: Sequence[EmbeddingBundleChunk],
    ) -> int:
        """Replace the chunk map rows of one unsealed bundle."""

        current = self._bundles.get(embedding_bundle_id)
        if current is not None and current.is_sealed:
            raise EmbeddingBundleInvalid("cannot rewrite the chunk map of a sealed bundle")
        self._chunks[embedding_bundle_id] = list(chunks)
        return len(chunks)

    def list_chunks(self, embedding_bundle_id: str) -> list[EmbeddingBundleChunk]:
        """Return the durable chunk map ordered by ``chunk_ordinal``."""

        return sorted(
            self._chunks.get(embedding_bundle_id, []),
            key=lambda chunk: chunk.chunk_ordinal,
        )

    def set_readiness_status(
        self,
        *,
        embedding_bundle_id: str,
        readiness_status: str,
    ) -> EmbeddingBundle:
        """Update the operational readiness projection of a sealed bundle."""

        bundle = self.get(embedding_bundle_id)
        updated = bundle.model_copy(update={"readiness_status": readiness_status})
        self._bundles[embedding_bundle_id] = updated
        return updated

    def list_bundles(self) -> list[EmbeddingBundle]:
        """Return every stored bundle."""

        return list(self._bundles.values())


class InMemoryReadinessCheckRepository:
    """Deterministic ``readiness_checks`` double."""

    def __init__(self) -> None:
        self._checks: dict[str, ReadinessCheck] = {}
        self._order: list[str] = []

    def record(self, check: ReadinessCheck) -> ReadinessCheck:
        """Persist one readiness check idempotently."""

        stored = check.model_copy(update={"created_at": check.created_at or _now()})
        if stored.check_id not in self._checks:
            self._order.append(stored.check_id)
        self._checks[stored.check_id] = stored
        return stored

    def latest(self, *, check_kind: str, subject_id: str) -> ReadinessCheck | None:
        """Return the most recent check for one subject."""

        for check_id in reversed(self._order):
            check = self._checks[check_id]
            if check.check_kind == check_kind and check.subject_id == subject_id:
                return check
        return None

    def list_checks(self) -> list[ReadinessCheck]:
        """Return every recorded check in insertion order."""

        return [self._checks[check_id] for check_id in self._order]
