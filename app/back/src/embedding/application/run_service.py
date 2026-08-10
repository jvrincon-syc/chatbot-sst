"""Embedding run use cases and the bounded single-writer executor.

Scope of one run (MVP): exactly one ``source_chunk_bundle_id`` and one
``embedding_profile_id``, because ``embedding_runs`` models a single source
bundle per row. Progress lives in ``summary_json``; per-chunk detail is read
back from ``embedding_bundle_chunks`` once the bundle is sealed.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import logging
import threading
from typing import Callable
from uuid import uuid4

from core.logging.observability import EventStatus, ObservabilityDomain, measure_duration_ms
from time import perf_counter

from embedding.application.bundle_builder import EmbeddingBundleBuilder
from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    ChunkBundleRepository,
    EmbeddingBundleRepository,
    EmbeddingEngineRegistry,
    EmbeddingProfileRepository,
    EmbeddingRunRepository,
)
from embedding.domain.errors import (
    EmbeddingDomainError,
    EmbeddingEngineNotFound,
    EmbeddingEngineUnavailable,
    EmbeddingExecutorBusy,
    EmbeddingProfileCompatibilityNotProven,
    IdempotencyConflict,
)
from embedding.domain.models import EmbeddingRun, canonical_json
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    FilesystemChunkBundleContentReader,
)


logger = logging.getLogger(__name__)

#: Maximum number of runs waiting for the single embedding worker.
DEFAULT_MAX_QUEUE_SIZE = 32
_TRANSACTION_STATUS_NAMES = {
    0: "idle",
    1: "active",
    2: "in_transaction",
    3: "in_error",
    4: "unknown",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _transaction_status(connection: object | None) -> str | None:
    if connection is None:
        return None
    getter = getattr(connection, "get_transaction_status", None)
    if not callable(getter):
        return None
    try:
        status = getter()
    except Exception:
        return "unavailable"
    if isinstance(status, int):
        return _TRANSACTION_STATUS_NAMES.get(status, f"code_{status}")
    return str(status)


def _failure_kind(exception: BaseException) -> str:
    message = str(exception).casefold()
    error_type = type(exception).__name__.casefold()
    if isinstance(exception, TimeoutError) or "timeout" in message or "timed out" in message:
        return "timeout"
    if "psycopg" in error_type or "sql" in message or "transaction" in message:
        return "database"
    if isinstance(exception, OSError):
        return "filesystem"
    if isinstance(exception, EmbeddingDomainError):
        return "domain"
    return "runtime"


def _commit_connection(
    connection: object | None,
    *,
    run_id: str | None = None,
    profile_id: str | None = None,
    provider: str | None = None,
    configuration_hash: str | None = None,
    phase: str,
) -> None:
    if connection is None:
        return
    commit = getattr(connection, "commit", None)
    if callable(commit):
        started_at = perf_counter()
        before = _transaction_status(connection)
        commit()
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_transaction_committed",
            status=EventStatus.COMPLETED,
            message="Embedding transaction committed",
            run_id=run_id,
            profile_id=profile_id,
            provider=provider,
            capability="embed",
            configuration_hash=configuration_hash,
            metrics={"duration_ms": measure_duration_ms(started_at)},
            attributes={
                "phase": phase,
                "transaction_status_before": before,
                "transaction_status_after": _transaction_status(connection),
            },
        )


def _rollback_connection(
    connection: object | None,
    *,
    run_id: str | None = None,
    profile_id: str | None = None,
    provider: str | None = None,
    configuration_hash: str | None = None,
    phase: str,
    exception: BaseException | None = None,
) -> None:
    if connection is None:
        return
    rollback = getattr(connection, "rollback", None)
    if callable(rollback):
        started_at = perf_counter()
        before = _transaction_status(connection)
        rollback()
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_transaction_rolled_back",
            status=EventStatus.WARNING,
            message="Embedding transaction rolled back",
            run_id=run_id,
            profile_id=profile_id,
            provider=provider,
            capability="embed",
            configuration_hash=configuration_hash,
            metrics={"duration_ms": measure_duration_ms(started_at)},
            attributes={
                "phase": phase,
                "failure_kind": _failure_kind(exception) if exception is not None else None,
                "transaction_status_before": before,
                "transaction_status_after": _transaction_status(connection),
            },
            exception=exception,
        )


def embedding_request_fingerprint(*, chunk_bundle_id: str, profile_id: str) -> str:
    """Return the deterministic fingerprint of one embedding run request."""

    return sha256(
        canonical_json({"chunk_bundle_id": chunk_bundle_id, "profile_id": profile_id}).encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class CreateEmbeddingRunRequest:
    """Public request payload: one chunk bundle, one profile."""

    chunk_bundle_id: str
    profile_id: str


class CreateEmbeddingRunUseCase:
    """Register one idempotent embedding run, failing closed on blocked profiles."""

    def __init__(
        self,
        *,
        runs: EmbeddingRunRepository,
        profiles: EmbeddingProfileRepository,
        chunk_bundles: ChunkBundleRepository,
        registry: EmbeddingEngineRegistry,
        connection: object | None = None,
    ) -> None:
        self._runs = runs
        self._profiles = profiles
        self._chunk_bundles = chunk_bundles
        self._registry = registry
        self._connection = connection

    def execute(
        self,
        *,
        request: CreateEmbeddingRunRequest,
        idempotency_key: str,
    ) -> EmbeddingRun:
        """Create or replay one run.

        Raises:
            EmbeddingProfileNotFound: When the profile does not exist.
            EmbeddingProfileCompatibilityNotProven: When it was never verified.
            ChunkBundleNotFound: When the source bundle is not registered.
            IdempotencyConflict: When the key was reused for another payload.
            EmbeddingEngineUnavailable: When no engine backs the profile.
        """

        try:
            phase_started_at = perf_counter()
            profile = self._profiles.get(request.profile_id)
            if not profile.can_embed_documents:
                raise EmbeddingProfileCompatibilityNotProven(
                    f"profile {profile.profile_id} is not enabled for document embedding"
                )
            chunk_bundle = self._chunk_bundles.get(request.chunk_bundle_id)
            chunk_bundle = self._chunk_bundles.ensure_registered(chunk_bundle)

            fingerprint = embedding_request_fingerprint(
                chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                profile_id=profile.profile_id,
            )
            existing = self._runs.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "idempotency key already maps to a different embedding request"
                    )
                _commit_connection(
                    self._connection,
                    run_id=existing.embedding_run_id,
                    profile_id=profile.profile_id,
                    provider=profile.provider,
                    configuration_hash=existing.configuration_fingerprint,
                    phase="create_reused_run",
                )
                emit_pipeline_event(
                    logger=logger,
                    domain=ObservabilityDomain.EMBEDDING,
                    event="embedding_run_reused",
                    status=EventStatus.REUSED,
                    message="Embedding run reused from idempotency key",
                    run_id=existing.embedding_run_id,
                    profile_id=profile.profile_id,
                    provider=profile.provider,
                    capability="embed",
                    configuration_hash=existing.configuration_fingerprint,
                    metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                    attributes={
                        "phase": "create_reused_run",
                        "source_chunk_bundle_id": existing.source_chunk_bundle_id,
                    },
                )
                return existing

            runtime = self._registry.get_runtime_status(profile)
            if not runtime.engine_available:
                raise EmbeddingEngineUnavailable(
                    f"no usable embedding engine for profile {profile.profile_id}"
                )

            run = EmbeddingRun(
                embedding_run_id=_run_id(idempotency_key=idempotency_key, fingerprint=fingerprint),
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                embedding_profile_id=profile.profile_id,
                configuration_fingerprint=profile.expected_fingerprint().value,
                runtime_engine=profile.provider,
                runtime_mode=runtime.runtime_mode,
                engine_revision_observed=runtime.engine_revision_observed,
                status="pending",
                summary={
                    "requested_children": chunk_bundle.child_count,
                    "embedded_children": 0,
                },
                created_at=_now(),
            )
            stored = self._runs.create(run)
            _commit_connection(
                self._connection,
                run_id=stored.embedding_run_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                configuration_hash=stored.configuration_fingerprint,
                phase="create_run",
            )
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=stored.embedding_run_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                configuration_hash=stored.configuration_fingerprint,
                metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                attributes={
                    "phase": "create_run",
                    "source_chunk_bundle_id": stored.source_chunk_bundle_id,
                    "requested_children": chunk_bundle.child_count,
                    "runtime_mode": runtime.runtime_mode,
                },
            )
        except Exception as error:
            _rollback_connection(
                self._connection,
                profile_id=request.profile_id,
                phase="create_run",
                exception=error,
            )
            raise
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_run_created",
            status=EventStatus.COMPLETED,
            message="Embedding run created",
            run_id=stored.embedding_run_id,
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="embed",
            configuration_hash=stored.configuration_fingerprint,
            attributes={
                "embedding_run_id": stored.embedding_run_id,
                "source_chunk_bundle_id": stored.source_chunk_bundle_id,
                "embedding_profile_id": stored.embedding_profile_id,
                "model": profile.model,
                "model_revision": profile.model_revision,
            },
        )
        return stored


class GetEmbeddingRunUseCase:
    """Read one durable embedding run."""

    def __init__(self, *, runs: EmbeddingRunRepository) -> None:
        self._runs = runs

    def execute(self, embedding_run_id: str) -> EmbeddingRun:
        """Return one run or raise ``EmbeddingRunNotFound``."""

        return self._runs.get(embedding_run_id)


class ListEmbeddingRunsUseCase:
    """List durable embedding runs, newest first."""

    def __init__(self, *, runs: EmbeddingRunRepository) -> None:
        self._runs = runs

    def execute(self) -> list[EmbeddingRun]:
        """Return every run."""

        return self._runs.list_runs()


class EmbeddingRunExecutor:
    """Single-writer executor with a bounded queue and transactional claims."""

    def __init__(
        self,
        *,
        runs: EmbeddingRunRepository,
        profiles: EmbeddingProfileRepository,
        chunk_bundles: ChunkBundleRepository,
        bundles: EmbeddingBundleRepository,
        registry: EmbeddingEngineRegistry,
        builder: EmbeddingBundleBuilder,
        content_reader: FilesystemChunkBundleContentReader,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        error_id_factory: Callable[[], str] = lambda: uuid4().hex,
        connection: object | None = None,
    ) -> None:
        self._runs = runs
        self._profiles = profiles
        self._chunk_bundles = chunk_bundles
        self._bundles = bundles
        self._registry = registry
        self._builder = builder
        self._content_reader = content_reader
        self._max_queue_size = max(1, max_queue_size)
        self._error_id_factory = error_id_factory
        self._connection = connection
        self._lock = threading.Lock()
        self._queued = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embedding-runner")

    def reconcile(self) -> list[str]:
        """Fail runs that a previous process left ``running``."""

        try:
            interrupted = self._runs.reconcile_interrupted()
            _commit_connection(self._connection, phase="reconcile_runs")
        except Exception as error:
            _rollback_connection(self._connection, phase="reconcile_runs", exception=error)
            raise
        for run_id in interrupted:
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_reconciled",
                status=EventStatus.WARNING,
                message="Interrupted embedding run reconciled to failed",
                run_id=run_id,
                capability="embed",
                attributes={"embedding_run_id": run_id},
            )
        return interrupted

    def submit(self, embedding_run_id: str) -> Future[None]:
        """Queue one run for the single worker.

        Raises:
            EmbeddingExecutorBusy: When the bounded queue is saturated.
        """

        with self._lock:
            if self._queued >= self._max_queue_size:
                emit_pipeline_event(
                    logger=logger,
                    domain=ObservabilityDomain.EMBEDDING,
                    event="embedding_run_queue_rejected",
                    status=EventStatus.REJECTED,
                    message="Embedding run rejected because the queue is saturated",
                    run_id=embedding_run_id,
                    capability="embed",
                    metrics={
                        "queue_depth": self._queued,
                        "max_queue_size": self._max_queue_size,
                    },
                    attributes={"phase": "submit_run"},
                )
                raise EmbeddingExecutorBusy("the embedding queue is saturated")
            self._queued += 1
            queued = self._queued
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_run_queued",
            status=EventStatus.STARTED,
            message="Embedding run queued",
            run_id=embedding_run_id,
            capability="embed",
            metrics={"queue_depth": queued, "max_queue_size": self._max_queue_size},
            attributes={"phase": "submit_run"},
        )
        return self._executor.submit(self._run_guarded, embedding_run_id)

    def close(self) -> None:
        """Drain the queue and release the worker thread."""

        self._executor.shutdown(wait=True, cancel_futures=False)

    def execute(self, embedding_run_id: str) -> EmbeddingRun:
        """Claim and execute one run in the calling thread."""

        try:
            claim_started_at = perf_counter()
            if not self._runs.claim(embedding_run_id):
                stored = self._runs.get(embedding_run_id)
                emit_pipeline_event(
                    logger=logger,
                    domain=ObservabilityDomain.EMBEDDING,
                    event="embedding_run_claim_skipped",
                    status=EventStatus.SKIPPED,
                    message="Embedding run claim skipped because the run is not pending",
                    run_id=stored.embedding_run_id,
                    profile_id=stored.embedding_profile_id,
                    provider=stored.runtime_engine,
                    capability="embed",
                    configuration_hash=stored.configuration_fingerprint,
                    metrics={"duration_ms": measure_duration_ms(claim_started_at)},
                    attributes={
                        "phase": "claim_run",
                        "status": stored.status,
                        "queue_depth": self._queued,
                    },
                )
                return stored
            _commit_connection(
                self._connection,
                run_id=embedding_run_id,
                phase="claim_run",
            )
            run = self._runs.get(embedding_run_id)
        except Exception as error:
            _rollback_connection(
                self._connection,
                run_id=embedding_run_id,
                phase="claim_run",
                exception=error,
            )
            raise
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_run_phase_completed",
            status=EventStatus.COMPLETED,
            message="Embedding run phase completed",
            run_id=run.embedding_run_id,
            profile_id=run.embedding_profile_id,
            provider=run.runtime_engine,
            capability="embed",
            configuration_hash=run.configuration_fingerprint,
            metrics={"duration_ms": measure_duration_ms(claim_started_at)},
            attributes={
                "phase": "claim_run",
                "queue_depth": self._queued,
                "max_queue_size": self._max_queue_size,
            },
        )

        started_at = perf_counter()
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_run_started",
            status=EventStatus.STARTED,
            message="Embedding run started",
            run_id=run.embedding_run_id,
            profile_id=run.embedding_profile_id,
            provider=run.runtime_engine,
            capability="embed",
            attributes={
                "embedding_run_id": run.embedding_run_id,
                "source_chunk_bundle_id": run.source_chunk_bundle_id,
                "embedding_profile_id": run.embedding_profile_id,
            },
        )
        try:
            stored = self._execute_claimed(run=run, started_at=started_at)
            _commit_connection(
                self._connection,
                run_id=stored.embedding_run_id,
                profile_id=stored.embedding_profile_id,
                provider=stored.runtime_engine,
                configuration_hash=stored.configuration_fingerprint,
                phase="persist_completed_run",
            )
            return stored
        except EmbeddingDomainError as error:
            return self._persist_failure(
                run=run,
                code=error.code,
                started_at=started_at,
                exception=error,
            )
        except Exception as error:
            internal_error_id = self._error_id_factory()
            logger.exception(
                "embedding_run_failed",
                extra={"internal_error_id": internal_error_id, "run_id": run.embedding_run_id},
            )
            return self._persist_failure(
                run=run,
                code="EMBEDDING_RUN_INTERNAL_ERROR",
                started_at=started_at,
                exception=error,
                internal_error_id=internal_error_id,
            )

    def _execute_claimed(self, *, run: EmbeddingRun, started_at: float) -> EmbeddingRun:
        try:
            phase = "load_source_bundle"
            phase_started_at = perf_counter()
            profile = self._profiles.get(run.embedding_profile_id)
            if not profile.can_embed_documents:
                raise EmbeddingProfileCompatibilityNotProven(
                    f"profile {profile.profile_id} is not enabled for document embedding"
                )
            chunk_bundle = self._chunk_bundles.get(run.source_chunk_bundle_id)
            content = self._content_reader.read(artifact_relpath=chunk_bundle.artifact_relpath)
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=run.embedding_run_id,
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                configuration_hash=run.configuration_fingerprint,
                metrics={
                    "duration_ms": measure_duration_ms(phase_started_at),
                    "child_count": len(content.children),
                    "parent_count": len(content.parents),
                },
                attributes={
                    "phase": phase,
                    "source_chunk_bundle_id": chunk_bundle.chunk_bundle_id,
                },
            )

            phase = "resolve_engine"
            phase_started_at = perf_counter()
            engine = self._registry.resolve_document_engine(profile)
            revision = engine.observe_revision()
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=run.embedding_run_id,
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                configuration_hash=run.configuration_fingerprint,
                metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                attributes={
                    "phase": phase,
                    "model_revision": revision,
                    "runtime_mode": run.runtime_mode,
                },
            )

            phase = "build_bundle"
            phase_started_at = perf_counter()
            built = self._builder.build(
                profile=profile,
                chunk_bundle=chunk_bundle,
                content=content,
                engine=engine,
                engine_revision_observed=revision,
            )
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=run.embedding_run_id,
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                configuration_hash=run.configuration_fingerprint,
                metrics={
                    "duration_ms": measure_duration_ms(phase_started_at),
                    "vector_count": built.bundle.vector_count,
                    "child_count": len(content.children),
                },
                attributes={
                    "phase": phase,
                    "embedding_bundle_id": built.bundle.embedding_bundle_id,
                },
            )

            duration_ms = measure_duration_ms(started_at)
            completed = run.model_copy(
                update={
                    "status": "completed",
                    "engine_revision_observed": revision,
                    "produced_embedding_bundle_id": built.bundle.embedding_bundle_id,
                    "completed_at": _now(),
                    "summary": {
                        "requested_children": len(content.children),
                        "embedded_children": built.bundle.vector_count,
                        "parent_count": len(content.parents),
                        "duration_ms": duration_ms,
                        "document_id": content.document_id,
                    },
                }
            )
            phase = "persist_completed_run"
            phase_started_at = perf_counter()
            stored = self._runs.update(completed)
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=stored.embedding_run_id,
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                configuration_hash=stored.configuration_fingerprint,
                metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                attributes={
                    "phase": phase,
                    "embedding_bundle_id": built.bundle.embedding_bundle_id,
                    "vector_count": built.bundle.vector_count,
                },
            )
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run completed",
                run_id=stored.embedding_run_id,
                document_id=content.document_id,
                profile_id=profile.profile_id,
                provider=profile.provider,
                capability="embed",
                metrics={"duration_ms": duration_ms, "vector_count": built.bundle.vector_count},
                attributes={
                    "embedding_run_id": stored.embedding_run_id,
                    "embedding_bundle_id": built.bundle.embedding_bundle_id,
                    "model_revision": revision,
                },
            )
            return stored
        except Exception as error:
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_failed",
                status=EventStatus.FAILED,
                message="Embedding run phase failed",
                run_id=run.embedding_run_id,
                profile_id=run.embedding_profile_id,
                provider=run.runtime_engine,
                capability="embed",
                configuration_hash=run.configuration_fingerprint,
                metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                attributes={
                    "phase": phase,
                    "failure_kind": _failure_kind(error),
                    "queue_depth": self._queued,
                },
                exception=error,
            )
            raise

    def _fail(
        self,
        *,
        run: EmbeddingRun,
        code: str,
        started_at: float,
        exception: BaseException,
        internal_error_id: str | None = None,
    ) -> EmbeddingRun:
        warnings = list(run.warnings)
        if internal_error_id is not None:
            warnings.append(f"internal_error_id={internal_error_id}")
        failed = run.model_copy(
            update={
                "status": "failed",
                "error_summary": code,
                "warnings": warnings,
                "completed_at": _now(),
                "summary": {
                    **run.summary,
                    "duration_ms": measure_duration_ms(started_at),
                },
            }
        )
        stored = self._runs.update(failed)
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.EMBEDDING,
            event="embedding_run_failed",
            status=EventStatus.FAILED,
            message="Embedding run failed",
            run_id=stored.embedding_run_id,
            profile_id=stored.embedding_profile_id,
            provider=stored.runtime_engine,
            capability="embed",
            attributes={
                "embedding_run_id": stored.embedding_run_id,
                "error_code": code,
                "internal_error_id": internal_error_id,
            },
            exception=exception,
        )
        return stored

    def _persist_failure(
        self,
        *,
        run: EmbeddingRun,
        code: str,
        started_at: float,
        exception: BaseException,
        internal_error_id: str | None = None,
    ) -> EmbeddingRun:
        _rollback_connection(
            self._connection,
            run_id=run.embedding_run_id,
            profile_id=run.embedding_profile_id,
            provider=run.runtime_engine,
            configuration_hash=run.configuration_fingerprint,
            phase="persist_failed_run",
            exception=exception,
        )
        try:
            phase_started_at = perf_counter()
            stored = self._fail(
                run=run,
                code=code,
                started_at=started_at,
                exception=exception,
                internal_error_id=internal_error_id,
            )
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_phase_completed",
                status=EventStatus.COMPLETED,
                message="Embedding run phase completed",
                run_id=stored.embedding_run_id,
                profile_id=stored.embedding_profile_id,
                provider=stored.runtime_engine,
                capability="embed",
                configuration_hash=stored.configuration_fingerprint,
                metrics={"duration_ms": measure_duration_ms(phase_started_at)},
                attributes={
                    "phase": "persist_failed_run",
                    "failure_kind": _failure_kind(exception),
                    "error_code": code,
                },
            )
            _commit_connection(
                self._connection,
                run_id=stored.embedding_run_id,
                profile_id=stored.embedding_profile_id,
                provider=stored.runtime_engine,
                configuration_hash=stored.configuration_fingerprint,
                phase="persist_failed_run",
            )
            return stored
        except Exception as error:
            _rollback_connection(
                self._connection,
                run_id=run.embedding_run_id,
                profile_id=run.embedding_profile_id,
                provider=run.runtime_engine,
                configuration_hash=run.configuration_fingerprint,
                phase="persist_failed_run",
                exception=error,
            )
            raise

    def _run_guarded(self, embedding_run_id: str) -> None:
        try:
            self.execute(embedding_run_id)
        finally:
            with self._lock:
                self._queued = max(0, self._queued - 1)
                queued = self._queued
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.EMBEDDING,
                event="embedding_run_queue_drained",
                status=EventStatus.COMPLETED,
                message="Embedding run queue depth updated",
                run_id=embedding_run_id,
                capability="embed",
                metrics={"queue_depth": queued, "max_queue_size": self._max_queue_size},
                attributes={"phase": "queue_finalize"},
            )


def _run_id(*, idempotency_key: str, fingerprint: str) -> str:
    digest = sha256(f"{idempotency_key}|{fingerprint}".encode("utf-8")).hexdigest()
    return f"embedding-run-{digest}"
