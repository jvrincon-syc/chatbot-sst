"""In-memory adapters for bundle-first indexing.

They reproduce the observable behaviour of the PostgreSQL adapters, including
append-only vector rows, per-document bundle activation inside one lane and the
transactional claim, so the same contract tests cover both implementations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading

from indexing.domain.bundle_first import (
    IndexingNodeRecord,
    IndexingRun,
    IndexingRunDocument,
)
from indexing.domain.errors import IndexingRunNotFound
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pgvector_store import VectorStoreWriteError
from indexing.infrastructure.postgres.vector_repository import AppendOnlyVectorRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryIndexingRunRepository:
    """Deterministic ``indexing_runs`` double with a transactional claim."""

    def __init__(self) -> None:
        self._runs: dict[str, IndexingRun] = {}
        self._by_key: dict[str, str] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def create(self, run: IndexingRun) -> IndexingRun:
        """Insert a run."""

        with self._lock:
            self._runs[run.run_id] = run
            self._order.append(run.run_id)
            if run.idempotency_key:
                self._by_key[run.idempotency_key] = run.run_id
        return run

    def get(self, run_id: str) -> IndexingRun:
        """Return one run or raise ``IndexingRunNotFound``."""

        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise IndexingRunNotFound(f"indexing run not found: {run_id}")
        return run

    def find_by_idempotency_key(self, idempotency_key: str) -> IndexingRun | None:
        """Return the run stored under one idempotency key."""

        with self._lock:
            run_id = self._by_key.get(idempotency_key)
            return self._runs.get(run_id) if run_id else None

    def list_runs(self) -> list[IndexingRun]:
        """Return every run, newest first."""

        with self._lock:
            return [self._runs[run_id] for run_id in reversed(self._order)]

    def claim(self, run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once."""

        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status != "pending":
                return False
            self._runs[run_id] = run.model_copy(
                update={"status": "running", "started_at": _now()}
            )
            return True

    def update(self, run: IndexingRun) -> IndexingRun:
        """Persist a durable state transition."""

        with self._lock:
            if run.run_id not in self._runs:
                raise IndexingRunNotFound(f"indexing run not found: {run.run_id}")
            self._runs[run.run_id] = run
        return run

    def list_running(self) -> list[IndexingRun]:
        """Return runs currently marked ``running``."""

        with self._lock:
            return [run for run in self._runs.values() if run.status == "running"]


class InMemoryIndexingRunDocumentRepository:
    """Deterministic ``indexing_run_documents`` double."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], IndexingRunDocument] = {}

    def upsert(self, document: IndexingRunDocument) -> IndexingRunDocument:
        """Insert or update one per-document row."""

        self._documents[(document.run_id, document.document_id)] = document
        return document

    def list_for_run(self, run_id: str) -> list[IndexingRunDocument]:
        """Return every document row of one run."""

        return [
            document
            for (stored_run_id, _document_id), document in self._documents.items()
            if stored_run_id == run_id
        ]


class InMemoryIndexingNodeWriter:
    """Deterministic ``indexing_nodes`` double."""

    def __init__(self) -> None:
        self.nodes: dict[str, IndexingNodeRecord] = {}

    def replace_scoped_nodes(
        self,
        *,
        project_id: str,
        source_chunk_bundle_id: str,
        nodes: Sequence[IndexingNodeRecord],
    ) -> int:
        """Replace the platform nodes of one bundle within one project."""

        stale = [
            node_id
            for node_id, node in self.nodes.items()
            if node.project_id == project_id
            and node.source_chunk_bundle_id == source_chunk_bundle_id
        ]
        for node_id in stale:
            del self.nodes[node_id]
        for node in nodes:
            self.nodes[node.node_id] = node
        return len(stale)


@dataclass
class _StoredVector:
    record: AppendOnlyVectorRecord
    embedding_profile_id: str
    indexing_target_id: str
    is_active: bool = False
    superseded_at: datetime | None = None


@dataclass
class InMemoryBundleVectorRepository:
    """Append-only vector store double with per-document activation and rollback."""

    rows: dict[tuple[str, str, str], _StoredVector] = field(default_factory=dict)

    def append_bundle_vectors(
        self,
        *,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        records: Sequence[AppendOnlyVectorRecord],
    ) -> int:
        """Insert inactive vector rows for one embedding bundle."""

        for record in records:
            if len(record.embedding) != profile.embedding_dimension:
                raise VectorStoreWriteError(
                    "embedding dimension does not match selected profile"
                )
        for record in records:
            key = (profile.vector_table, record.embedding_bundle_id, record.node_id)
            self.rows[key] = _StoredVector(
                record=record,
                embedding_profile_id=profile.profile_id,
                indexing_target_id=indexing_target_id,
                is_active=False,
            )
        return len(records)

    def activate_bundle(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> None:
        """Activate one bundle and supersede only prior active rows of its documents."""

        activated_document_ids = {
            stored.record.document_id
            for stored in self.rows.values()
            if stored.record.embedding_bundle_id == embedding_bundle_id
            and self._same_lane(
                stored,
                project_id=project_id,
                profile=profile,
                indexing_target_id=indexing_target_id,
                corpus_version=corpus_version,
            )
        }
        for stored in self.rows.values():
            if not self._same_lane(
                stored,
                project_id=project_id,
                profile=profile,
                indexing_target_id=indexing_target_id,
                corpus_version=corpus_version,
            ):
                continue
            if stored.record.embedding_bundle_id == embedding_bundle_id:
                stored.is_active = True
                stored.superseded_at = None
            elif stored.is_active and stored.record.document_id in activated_document_ids:
                stored.is_active = False
                stored.superseded_at = _now()

    def rollback_to_bundle(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        current_embedding_bundle_id: str,
        previous_embedding_bundle_id: str,
    ) -> None:
        """Deactivate the current bundle and reactivate a validated previous one."""

        for stored in self.rows.values():
            if not self._same_lane(
                stored,
                project_id=project_id,
                profile=profile,
                indexing_target_id=indexing_target_id,
                corpus_version=corpus_version,
            ):
                continue
            if stored.record.embedding_bundle_id == current_embedding_bundle_id:
                stored.is_active = False
                stored.superseded_at = _now()
            elif stored.record.embedding_bundle_id == previous_embedding_bundle_id:
                stored.is_active = True
                stored.superseded_at = None

    def count_active_rows(
        self,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
        embedding_bundle_id: str,
    ) -> int:
        """Count active rows for one bundle in one lane."""

        return sum(
            1
            for stored in self.rows.values()
            if stored.is_active
            and stored.record.embedding_bundle_id == embedding_bundle_id
            and self._same_lane(
                stored,
                project_id=project_id,
                profile=profile,
                indexing_target_id=indexing_target_id,
                corpus_version=corpus_version,
            )
        )

    def active_rows(self) -> list[_StoredVector]:
        """Return every active row, for assertions and readiness reads."""

        return [stored for stored in self.rows.values() if stored.is_active]

    @staticmethod
    def _same_lane(
        stored: _StoredVector,
        *,
        project_id: str,
        profile: ResolvedIndexingProfile,
        indexing_target_id: str,
        corpus_version: str,
    ) -> bool:
        return (
            stored.record.project_id == project_id
            and
            stored.embedding_profile_id == profile.profile_id
            and stored.indexing_target_id == indexing_target_id
            and stored.record.corpus_version == corpus_version
        )
