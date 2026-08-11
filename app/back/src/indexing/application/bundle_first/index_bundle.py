"""Bundle-first indexing: consume pre-computed vectors, never produce them.

This module contains zero calls to ``EmbeddingFactory``, ``embed_documents()``
or ``document.profile``. It loads a sealed :class:`EmbeddingBundle`, reads the
vectors back from the artifact store, adapts the source chunk bundle into nodes
without re-chunking and appends inactive vector rows. Activation is a separate
use case.
"""

from __future__ import annotations

from contextlib import nullcontext
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime, timezone
import logging
import threading
from typing import Callable
from uuid import uuid4

from core.logging.observability import EventStatus, ObservabilityDomain, measure_duration_ms
from time import perf_counter

from embedding.application.events import emit_pipeline_event
from embedding.application.ports import (
    ChunkBundleRepository,
    EmbeddingBundleRepository,
    EmbeddingProfileRepository,
    ReadinessCheckRepository,
)
from embedding.domain.errors import (
    EmbeddingBundleInvalid,
    EmbeddingBundleStale,
    EmbeddingDomainError,
    EmbeddingProfileCompatibilityNotProven,
)
from embedding.domain.models import (
    EmbeddingBundle,
    EmbeddingBundleChunk,
    EmbeddingProfile,
    ReadinessCheck,
)
from embedding.infrastructure.filesystem.artifact_store import (
    FilesystemEmbeddingBundleArtifactStore,
)
from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    ChunkBundleContent,
    FilesystemChunkBundleContentReader,
)
from indexing.application.bundle_first.ports import (
    BundleVectorWriter,
    IndexingNodeWriter,
    IndexingRunDocumentRepository,
    IndexingRunRepository,
    IndexingTargetRepository,
    TransactionManager,
    resolved_profile_from_embedding_profile,
)
from indexing.domain.bundle_first import (
    IndexingNodeRecord,
    IndexingRun,
    IndexingRunDocument,
    IndexingTarget,
    indexing_request_fingerprint,
)
from indexing.domain.errors import (
    IndexingDomainError,
    IndexingExecutorBusy,
    IndexingIdempotencyConflict,
    IndexingTargetIncompatible,
)
from indexing.infrastructure.postgres.vector_repository import AppendOnlyVectorRecord
from rag_platform.domain.identity import physical_node_id


logger = logging.getLogger(__name__)

#: Maximum number of indexing runs waiting for the single worker.
DEFAULT_MAX_QUEUE_SIZE = 16


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _NullTransactionManager:
    """Transaction manager for in-memory wiring and dry-run."""

    def transaction(self):
        """Return a no-op scope."""

        return nullcontext()


@dataclass(frozen=True)
class IndexEmbeddingBundleResult:
    """Outcome of indexing one embedding bundle."""

    run_id: str
    embedding_bundle_id: str
    indexing_target_id: str
    committed_documents: int
    parent_nodes: int
    child_nodes: int
    vector_rows: int


def build_nodes(
    *,
    content: ChunkBundleContent,
    chunk_bundle_id: str,
    chunking_bundle_fingerprint: str,
    chunking_version: str,
    ingestion_origin: str,
    project_id: str | None = None,
) -> list[IndexingNodeRecord]:
    """Adapt a persisted chunk bundle into durable node records.

    Namespacing is **gated** (ADR-007 §2, C-9):

    - ``project_id is None`` (legacy): the chunk ids become the node ids verbatim
      (``node_id == source_chunk_id``), so the output is byte-for-byte identical to
      the pre-Fase-4 behaviour and the child chunk map still aligns without
      re-chunking. The physical-identity fields stay ``None``.
    - ``project_id`` present (platform): ``node_id`` is the namespaced
      :func:`physical_node_id` and, for children, ``parent_node_id`` is the physical
      id of the parent chunk (``physical_node_id(..., source_parent_chunk_id)``), so
      parent→child expansion uses the physical parent, never the source chunk id.
      Two projects that share a ``source_chunk_id`` get distinct ``node_id``.
    """

    def _node_id(source_chunk_id: str) -> str:
        if project_id is None:
            return source_chunk_id
        return physical_node_id(
            project_id=project_id,
            source_chunk_bundle_id=chunk_bundle_id,
            source_chunk_id=source_chunk_id,
        )

    nodes: list[IndexingNodeRecord] = []
    for parent in content.parents:
        nodes.append(
            IndexingNodeRecord(
                node_id=_node_id(parent.chunk_id),
                project_id=project_id,
                document_id=content.document_id,
                source_relpath=content.source_relpath,
                source_hash=content.source_hash,
                ingestion_origin=ingestion_origin,
                node_role="parent",
                parent_node_id=None,
                source_chunk_id=parent.chunk_id if project_id is not None else None,
                source_parent_chunk_id=None,
                chunk_index=parent.ordinal,
                page_start=parent.source_span.page_start,
                page_end=parent.source_span.page_end,
                text=parent.text,
                metadata={
                    "node_role": "parent",
                    "document_id": content.document_id,
                    "chunking_profile_id": parent.profile_id,
                    "ordinal": parent.ordinal,
                    "block_ids": list(parent.block_ids),
                    "char_start": parent.source_span.char_start,
                    "char_end": parent.source_span.char_end,
                    "corpus_version": content.corpus_version,
                },
                chunking_version=chunking_version,
                processing_fingerprint=chunking_bundle_fingerprint,
                source_chunk_bundle_id=chunk_bundle_id,
                chunking_bundle_fingerprint=chunking_bundle_fingerprint,
                corpus_version=content.corpus_version,
            )
        )
    for child in content.children:
        nodes.append(
            IndexingNodeRecord(
                node_id=_node_id(child.chunk_id),
                project_id=project_id,
                document_id=content.document_id,
                source_relpath=content.source_relpath,
                source_hash=content.source_hash,
                ingestion_origin=ingestion_origin,
                node_role="child",
                parent_node_id=_node_id(child.parent_id),
                source_chunk_id=child.chunk_id if project_id is not None else None,
                source_parent_chunk_id=(
                    child.parent_id if project_id is not None else None
                ),
                chunk_index=child.ordinal,
                page_start=child.source_span.page_start,
                page_end=child.source_span.page_end,
                text=child.text,
                metadata={
                    "node_role": "child",
                    "document_id": content.document_id,
                    "parent_node_id": child.parent_id,
                    "chunking_profile_id": child.profile_id,
                    "ordinal": child.ordinal,
                    "context_prefix": child.context_prefix,
                    "char_start": child.source_span.char_start,
                    "char_end": child.source_span.char_end,
                    "token_count": child.token_count,
                    "corpus_version": content.corpus_version,
                },
                chunking_version=chunking_version,
                processing_fingerprint=chunking_bundle_fingerprint,
                source_chunk_bundle_id=chunk_bundle_id,
                chunking_bundle_fingerprint=chunking_bundle_fingerprint,
                corpus_version=content.corpus_version,
            )
        )
    return nodes


def _build_vector_record(
    *,
    chunk: EmbeddingBundleChunk,
    bundle: EmbeddingBundle,
    profile: EmbeddingProfile,
    chunk_bundle_id: str,
    project_id: str | None,
    child_nodes_by_source_chunk_id: dict[str, IndexingNodeRecord],
    vector: list[float],
) -> AppendOnlyVectorRecord:
    """Align one vector row with the durable child-node identity.

    Legacy keeps ``node_id == child_chunk_id`` and the original metadata payload.
    Platform rows carry the namespaced physical ``node_id`` plus ``project_id`` and
    preserve the source chunk ids explicitly for traceability.
    """

    child_node = child_nodes_by_source_chunk_id.get(chunk.child_chunk_id)
    if child_node is None:
        raise EmbeddingBundleInvalid(
            "chunk map is not aligned with the built child nodes"
        )

    metadata = {
        "document_id": chunk.document_id,
        "parent_node_id": (
            child_node.parent_node_id
            if project_id is not None
            else chunk.parent_chunk_id
        ),
        "child_chunk_id": chunk.child_chunk_id,
        "chunk_ordinal": chunk.chunk_ordinal,
        "embedding_bundle_id": bundle.embedding_bundle_id,
        "embedding_profile_id": profile.profile_id,
        "corpus_version": bundle.corpus_version,
        "source_chunk_bundle_id": chunk_bundle_id,
    }
    if project_id is not None:
        metadata["source_parent_chunk_id"] = chunk.parent_chunk_id

    return AppendOnlyVectorRecord(
        node_id=child_node.node_id,
        document_id=chunk.document_id,
        embedding=vector,
        metadata=metadata,
        embedding_bundle_id=bundle.embedding_bundle_id,
        corpus_version=bundle.corpus_version,
        configuration_fingerprint=bundle.configuration_fingerprint,
        vector_checksum=str(chunk.vector_checksum or ""),
        project_id=project_id,
    )


class IndexEmbeddingBundleUseCase:
    """Persist one sealed embedding bundle into its resolved indexing target."""

    def __init__(
        self,
        *,
        profiles: EmbeddingProfileRepository,
        chunk_bundles: ChunkBundleRepository,
        bundles: EmbeddingBundleRepository,
        targets: IndexingTargetRepository,
        nodes: IndexingNodeWriter,
        vectors: BundleVectorWriter,
        artifacts: FilesystemEmbeddingBundleArtifactStore,
        content_reader: FilesystemChunkBundleContentReader,
        run_documents: IndexingRunDocumentRepository,
        readiness_checks: ReadinessCheckRepository,
        transactions: TransactionManager | None = None,
    ) -> None:
        self._profiles = profiles
        self._chunk_bundles = chunk_bundles
        self._bundles = bundles
        self._targets = targets
        self._nodes = nodes
        self._vectors = vectors
        self._artifacts = artifacts
        self._content_reader = content_reader
        self._run_documents = run_documents
        self._readiness_checks = readiness_checks
        self._transactions = transactions or _NullTransactionManager()

    def resolve_target(self, profile: EmbeddingProfile, bundle: EmbeddingBundle) -> IndexingTarget:
        """Resolve the target from the profile, never from client input.

        Raises:
            IndexingTargetIncompatible: When no compatible active target exists.
        """

        target_id = profile.default_indexing_target_id
        if target_id is None:
            raise IndexingTargetIncompatible(
                f"profile {profile.profile_id} has no default_indexing_target_id"
            )
        try:
            target = self._targets.get(target_id)
        except LookupError as error:
            raise IndexingTargetIncompatible(
                f"indexing target {target_id} does not exist"
            ) from error
        if not target.active:
            raise IndexingTargetIncompatible(f"indexing target {target_id} is not active")
        if target.vector_table != profile.vector_table:
            raise IndexingTargetIncompatible(
                "indexing target does not point at the profile vector table"
            )
        if not target.accepts_metric(bundle.distance_metric):
            raise IndexingTargetIncompatible(
                "indexing target operator class does not match the bundle metric"
            )
        return target

    def execute(self, *, run: IndexingRun, embedding_bundle_id: str) -> IndexEmbeddingBundleResult:
        """Index one bundle, committing per document and leaving rows inactive.

        Raises:
            EmbeddingBundleInvalid: When the bundle is not sealed and validated.
            EmbeddingBundleStale: When the source content drifted.
            EmbeddingProfileCompatibilityNotProven: When the profile is blocked.
            IndexingTargetIncompatible: When no compatible target exists.
        """

        bundle = self._bundles.get(embedding_bundle_id)
        if not bundle.is_sealed:
            raise EmbeddingBundleInvalid(
                f"embedding bundle {embedding_bundle_id} is not sealed and validated"
            )
        profile = self._profiles.get(bundle.embedding_profile_id)
        if not profile.can_embed_documents:
            raise EmbeddingProfileCompatibilityNotProven(
                f"profile {profile.profile_id} is not enabled for document embedding"
            )
        if bundle.configuration_fingerprint != profile.expected_fingerprint().value:
            raise EmbeddingBundleStale(
                "bundle fingerprint no longer matches the durable profile"
            )

        target = self.resolve_target(profile, bundle)
        chunk_bundle = self._chunk_bundles.get(bundle.source_chunk_bundle_id)
        content = self._content_reader.read(artifact_relpath=chunk_bundle.artifact_relpath)
        if content.source_content_fingerprint != bundle.source_content_fingerprint:
            raise EmbeddingBundleStale(
                "source chunk bundle content changed after the bundle was sealed"
            )

        chunk_map = self._bundles.list_chunks(embedding_bundle_id)
        if len(chunk_map) != len(content.children):
            raise EmbeddingBundleInvalid("chunk map does not cover the source child chunks")
        vectors = self._artifacts.load_vectors(
            vector_artifact_relpath=str(bundle.vector_artifact_relpath)
        )
        if len(vectors) != bundle.vector_count:
            raise EmbeddingBundleInvalid("vector artifact does not match the recorded count")

        child_ids = {child.chunk_id for child in content.children}
        if {chunk.child_chunk_id for chunk in chunk_map} != child_ids:
            raise EmbeddingBundleStale("chunk map is not aligned with the source child chunks")

        project_id = chunk_bundle.project_id
        nodes = build_nodes(
            content=content,
            chunk_bundle_id=chunk_bundle.chunk_bundle_id,
            chunking_bundle_fingerprint=chunk_bundle.bundle_fingerprint,
            chunking_version=chunk_bundle.profile_id,
            ingestion_origin=profile.ingestion_origin,
            project_id=project_id,
        )
        child_nodes_by_source_chunk_id = {
            (node.source_chunk_id or node.node_id): node
            for node in nodes
            if node.node_role == "child"
        }
        records = [
            _build_vector_record(
                chunk=chunk,
                bundle=bundle,
                profile=profile,
                chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                project_id=project_id,
                child_nodes_by_source_chunk_id=child_nodes_by_source_chunk_id,
                vector=list(vectors[chunk.vector_offset]),
            )
            for chunk in chunk_map
        ]

        resolved_profile = resolved_profile_from_embedding_profile(profile)
        started_at = _now()
        self._run_documents.upsert(
            IndexingRunDocument(
                run_id=run.run_id,
                document_id=content.document_id,
                source_relpath=content.source_relpath,
                source_hash=content.source_hash,
                ingestion_origin=profile.ingestion_origin,
                eligibility_status="included",
                eligibility_reason="embedding_bundle_ready",
                source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                embedding_bundle_id=bundle.embedding_bundle_id,
                status="running",
                started_at=started_at,
            )
        )

        parent_nodes = sum(1 for node in nodes if node.node_role == "parent")
        child_nodes = len(nodes) - parent_nodes
        with self._transactions.transaction():
            if project_id is None:
                self._nodes.replace_document_nodes(
                    document_id=content.document_id,
                    nodes=nodes,
                )
            else:
                self._nodes.replace_scoped_nodes(
                    project_id=project_id,
                    source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                    nodes=nodes,
                )
            written = self._vectors.append_bundle_vectors(
                profile=resolved_profile,
                indexing_target_id=target.indexing_target_id,
                records=records,
            )
        committed_at = _now()
        self._run_documents.upsert(
            IndexingRunDocument(
                run_id=run.run_id,
                document_id=content.document_id,
                source_relpath=content.source_relpath,
                source_hash=content.source_hash,
                ingestion_origin=profile.ingestion_origin,
                eligibility_status="included",
                eligibility_reason="embedding_bundle_ready",
                indexed_parent_nodes=parent_nodes,
                indexed_child_nodes=child_nodes,
                source_chunk_bundle_id=chunk_bundle.chunk_bundle_id,
                embedding_bundle_id=bundle.embedding_bundle_id,
                status="committed",
                parent_count=parent_nodes,
                child_count=child_nodes,
                vector_count=written,
                started_at=started_at,
                completed_at=committed_at,
                committed_at=committed_at,
            )
        )
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexing_document_committed",
            status=EventStatus.COMPLETED,
            message="Indexing document committed",
            run_id=run.run_id,
            document_id=content.document_id,
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="index",
            metrics={"vector_rows": written, "parent_nodes": parent_nodes},
            attributes={
                "indexing_run_id": run.run_id,
                "embedding_bundle_id": bundle.embedding_bundle_id,
                "embedding_profile_id": profile.profile_id,
                "indexing_target_id": target.indexing_target_id,
            },
        )
        report: dict[str, object] = {
            "committed_documents": 1,
            "parent_nodes": parent_nodes,
            "child_nodes": child_nodes,
            "vector_rows": written,
        }
        self._readiness_checks.record(
            ReadinessCheck(
                check_id=ReadinessCheck.deterministic_id(
                    check_kind="indexing_readiness",
                    subject_id=bundle.embedding_bundle_id,
                    report=report,
                ),
                check_kind="indexing_readiness",
                subject_id=bundle.embedding_bundle_id,
                embedding_profile_id=profile.profile_id,
                indexing_target_id=target.indexing_target_id,
                status="passed" if written == len(records) else "failed",
                report=report,
            )
        )
        return IndexEmbeddingBundleResult(
            run_id=run.run_id,
            embedding_bundle_id=bundle.embedding_bundle_id,
            indexing_target_id=target.indexing_target_id,
            committed_documents=1,
            parent_nodes=parent_nodes,
            child_nodes=child_nodes,
            vector_rows=written,
        )


@dataclass(frozen=True)
class CreateIndexingRunRequest:
    """Public payload: only the embedding bundle id."""

    embedding_bundle_id: str


class CreateIndexingRunUseCase:
    """Register one idempotent bundle-first indexing run."""

    def __init__(
        self,
        *,
        runs: IndexingRunRepository,
        bundles: EmbeddingBundleRepository,
        profiles: EmbeddingProfileRepository,
        index_use_case: IndexEmbeddingBundleUseCase,
    ) -> None:
        self._runs = runs
        self._bundles = bundles
        self._profiles = profiles
        self._index_use_case = index_use_case

    def execute(
        self,
        *,
        request: CreateIndexingRunRequest,
        idempotency_key: str,
    ) -> IndexingRun:
        """Create or replay one run.

        Raises:
            EmbeddingBundleNotFound: When the bundle does not exist.
            EmbeddingBundleInvalid: When it is not sealed.
            IndexingTargetIncompatible: When the profile has no usable target.
            IndexingIdempotencyConflict: When the key was reused.
        """

        bundle = self._bundles.get(request.embedding_bundle_id)
        if not bundle.is_sealed:
            raise EmbeddingBundleInvalid(
                f"embedding bundle {bundle.embedding_bundle_id} is not sealed"
            )
        profile = self._profiles.get(bundle.embedding_profile_id)
        target = self._index_use_case.resolve_target(profile, bundle)

        fingerprint = indexing_request_fingerprint(
            embedding_bundle_id=bundle.embedding_bundle_id
        )
        existing = self._runs.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise IndexingIdempotencyConflict(
                    "idempotency key already maps to a different indexing request"
                )
            return existing

        run = IndexingRun(
            run_id=_run_id(idempotency_key=idempotency_key, fingerprint=fingerprint),
            profile_id=profile.profile_id,
            status="pending",
            config_hash=profile.config_hash,
            embedding_bundle_id=bundle.embedding_bundle_id,
            embedding_profile_id=profile.profile_id,
            indexing_target_id=target.indexing_target_id,
            corpus_version=bundle.corpus_version,
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            validation_status="pending",
            activation_status="pending",
            summary={"requested_documents": 1, "committed_documents": 0},
        )
        stored = self._runs.create(run)
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexing_run_created",
            status=EventStatus.COMPLETED,
            message="Indexing run created",
            run_id=stored.run_id,
            profile_id=profile.profile_id,
            provider=profile.provider,
            capability="index",
            attributes={
                "indexing_run_id": stored.run_id,
                "embedding_bundle_id": bundle.embedding_bundle_id,
                "embedding_profile_id": profile.profile_id,
                "indexing_target_id": target.indexing_target_id,
            },
        )
        return stored


class GetIndexingRunUseCase:
    """Read one durable indexing run."""

    def __init__(self, *, runs: IndexingRunRepository) -> None:
        self._runs = runs

    def execute(self, run_id: str) -> IndexingRun:
        """Return one run or raise ``IndexingRunNotFound``."""

        return self._runs.get(run_id)


class ListIndexingRunsUseCase:
    """List durable indexing runs, newest first."""

    def __init__(self, *, runs: IndexingRunRepository) -> None:
        self._runs = runs

    def execute(self) -> list[IndexingRun]:
        """Return every run."""

        return self._runs.list_runs()


class IndexingRunExecutor:
    """Single-writer executor with a bounded queue and transactional claims."""

    def __init__(
        self,
        *,
        runs: IndexingRunRepository,
        index_use_case: IndexEmbeddingBundleUseCase,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        error_id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._runs = runs
        self._index_use_case = index_use_case
        self._max_queue_size = max(1, max_queue_size)
        self._error_id_factory = error_id_factory
        self._lock = threading.Lock()
        self._queued = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indexing-runner")

    def submit(self, run_id: str) -> Future[None]:
        """Queue one run for the single worker.

        Raises:
            IndexingExecutorBusy: When the bounded queue is saturated.
        """

        with self._lock:
            if self._queued >= self._max_queue_size:
                raise IndexingExecutorBusy("the indexing queue is saturated")
            self._queued += 1
        return self._executor.submit(self._run_guarded, run_id)

    def close(self) -> None:
        """Drain the queue and release the worker thread."""

        self._executor.shutdown(wait=True, cancel_futures=False)

    def execute(self, run_id: str) -> IndexingRun:
        """Claim and execute one run in the calling thread."""

        if not self._runs.claim(run_id):
            return self._runs.get(run_id)
        run = self._runs.get(run_id)
        started_at = perf_counter()
        try:
            result = self._index_use_case.execute(
                run=run,
                embedding_bundle_id=str(run.embedding_bundle_id),
            )
        except (EmbeddingDomainError, IndexingDomainError) as error:
            return self._fail(run=run, code=error.code, exception=error)
        except (OSError, ValueError, RuntimeError) as error:
            internal_error_id = self._error_id_factory()
            logger.exception(
                "indexing_run_failed",
                extra={"internal_error_id": internal_error_id, "run_id": run.run_id},
            )
            return self._fail(
                run=run,
                code="INDEXING_RUN_INTERNAL_ERROR",
                exception=error,
                internal_error_id=internal_error_id,
            )

        completed = run.model_copy(
            update={
                "status": "completed",
                "validation_status": "passed",
                "completed_at": _now(),
                "summary": {
                    "requested_documents": 1,
                    "committed_documents": result.committed_documents,
                    "parent_nodes": result.parent_nodes,
                    "child_nodes": result.child_nodes,
                    "vector_rows": result.vector_rows,
                    "duration_ms": measure_duration_ms(started_at),
                },
            }
        )
        stored = self._runs.update(completed)
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexing_run_completed",
            status=EventStatus.COMPLETED,
            message="Indexing run completed",
            run_id=stored.run_id,
            profile_id=stored.embedding_profile_id,
            capability="index",
            metrics={"vector_rows": result.vector_rows},
            attributes={
                "indexing_run_id": stored.run_id,
                "embedding_bundle_id": result.embedding_bundle_id,
                "indexing_target_id": result.indexing_target_id,
            },
        )
        return stored

    def _fail(
        self,
        *,
        run: IndexingRun,
        code: str,
        exception: BaseException,
        internal_error_id: str | None = None,
    ) -> IndexingRun:
        warnings = list(run.warnings)
        if internal_error_id is not None:
            warnings.append(f"internal_error_id={internal_error_id}")
        failed = run.model_copy(
            update={
                "status": "failed",
                "validation_status": "failed",
                "completed_at": _now(),
                "warnings": [*warnings, code],
                "summary": {**run.summary, "error_code": code},
            }
        )
        stored = self._runs.update(failed)
        emit_pipeline_event(
            logger=logger,
            domain=ObservabilityDomain.INDEXING,
            event="indexing_run_failed",
            status=EventStatus.FAILED,
            message="Indexing run failed",
            run_id=stored.run_id,
            profile_id=stored.embedding_profile_id,
            capability="index",
            attributes={
                "indexing_run_id": stored.run_id,
                "error_code": code,
                "internal_error_id": internal_error_id,
            },
            exception=exception,
        )
        return stored

    def _run_guarded(self, run_id: str) -> None:
        try:
            self.execute(run_id)
        finally:
            with self._lock:
                self._queued = max(0, self._queued - 1)


class IndexingRunReconciler:
    """Resolve runs left ``running`` by a process that never finished."""

    def __init__(
        self,
        *,
        runs: IndexingRunRepository,
        run_documents: IndexingRunDocumentRepository,
    ) -> None:
        self._runs = runs
        self._run_documents = run_documents

    def reconcile(self) -> list[IndexingRun]:
        """Mark interrupted runs failed, preserving partial commits in the summary."""

        reconciled: list[IndexingRun] = []
        for run in self._runs.list_running():
            documents = self._run_documents.list_for_run(run.run_id)
            committed = sum(1 for document in documents if document.status == "committed")
            requested = int(run.summary.get("requested_documents", len(documents) or 1))
            updated = run.model_copy(
                update={
                    "status": "failed",
                    "validation_status": "failed",
                    "completed_at": _now(),
                    "warnings": [*run.warnings, "INDEXING_RUN_INTERRUPTED"],
                    "summary": {
                        **run.summary,
                        "requested_documents": requested,
                        "committed_documents": committed,
                        "interrupted": True,
                    },
                }
            )
            reconciled.append(self._runs.update(updated))
            emit_pipeline_event(
                logger=logger,
                domain=ObservabilityDomain.INDEXING,
                event="indexing_run_reconciled",
                status=EventStatus.WARNING,
                message="Interrupted indexing run reconciled",
                run_id=run.run_id,
                capability="index",
                metrics={"committed_documents": committed},
                attributes={"indexing_run_id": run.run_id},
            )
        return reconciled


def _run_id(*, idempotency_key: str, fingerprint: str) -> str:
    digest = sha256(f"{idempotency_key}|{fingerprint}".encode("utf-8")).hexdigest()
    return f"indexing-run-{digest}"
