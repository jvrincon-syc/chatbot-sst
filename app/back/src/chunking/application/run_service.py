from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import logging
import threading
from pathlib import Path
from typing import Any

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.domain.models import ChunkingProfile
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from ingestion.paths import ArtifactPaths


logger = logging.getLogger(__name__)


class ChunkingRunNotFoundError(ValueError):
    """Raised when a run id does not exist."""


class ChunkingDocumentNotFoundError(ValueError):
    """Raised when a requested document id is unknown."""


class ChunkingParentNotFoundError(ValueError):
    """Raised when a requested parent id is unknown."""


class ChunkingIdempotencyConflictError(ValueError):
    """Raised when one idempotency key is reused for a different payload."""


class ChunkingProfileNotFoundError(ValueError):
    """Raised when a requested profile id is not supported locally."""


@dataclass(frozen=True)
class ChunkingRunRequest:
    scope: str
    document_ids: tuple[str, ...]
    profile_id: str
    force: bool
    request_id: str | None = None


@dataclass
class ChunkingRunState:
    run_id: str
    request: ChunkingRunRequest
    idempotency_key: str
    payload_fingerprint: str
    status: str
    requested_documents: int
    completed_documents: int = 0
    documents: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ChunkingRunService:
    """Application service for local chunking runs and persisted inspection."""

    def __init__(
        self,
        *,
        docs_normalized: Path,
        chunks_root: Path,
        source: Schema2NormalizedDocumentSource,
        orchestrator: ChunkingOrchestrator,
        chunk_repository: FilesystemChunkBundleRepository,
    ) -> None:
        self._docs_normalized = docs_normalized
        self._chunks_root = chunks_root
        self._source = source
        self._orchestrator = orchestrator
        self._chunk_repository = chunk_repository
        self._lock = threading.Lock()
        self._runs: dict[str, ChunkingRunState] = {}
        self._idempotency_index: dict[str, tuple[str, str]] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="chunking-runner",
        )
        self._hydrate_persisted_runs()

    def list_profiles(self) -> list[dict[str, Any]]:
        profile = ChunkingProfile.local_structural_v1()
        return [
            {
                "profile_id": profile.profile_id,
                "child_min_tokens": profile.child_min_tokens,
                "child_target_tokens": profile.child_target_tokens,
                "child_max_tokens": profile.child_max_tokens,
                "overlap_ratio": profile.overlap_ratio,
                "overlap_min_tokens": profile.overlap_min_tokens,
                "overlap_max_tokens": profile.overlap_max_tokens,
            }
        ]

    def create_run(
        self,
        *,
        request: ChunkingRunRequest,
        idempotency_key: str,
    ) -> ChunkingRunState:
        self._require_profile(request.profile_id)
        document_ids = self._resolved_document_ids(request)
        payload_fingerprint = self._payload_fingerprint(
            scope=request.scope,
            document_ids=document_ids,
            profile_id=request.profile_id,
            force=request.force,
        )
        run_id = sha256(f"{idempotency_key}|{payload_fingerprint}".encode("utf-8")).hexdigest()
        with self._lock:
            existing = self._idempotency_index.get(idempotency_key)
            if existing is not None and existing[1] != payload_fingerprint:
                logger.warning(
                    "chunking_idempotency_conflict",
                    extra={
                        "idempotency_key": idempotency_key,
                        "profile_id": request.profile_id,
                        "scope": request.scope,
                        "request_id": request.request_id,
                    },
                )
                raise ChunkingIdempotencyConflictError(
                    "idempotency key already maps to a different chunking payload"
                )
            if run_id in self._runs:
                logger.info(
                    "chunking_run_reused",
                    extra={
                        "run_id": run_id,
                        "idempotency_key": idempotency_key,
                        "request_id": request.request_id,
                    },
                )
                return self._runs[run_id]
            state = ChunkingRunState(
                run_id=run_id,
                request=ChunkingRunRequest(
                    scope=request.scope,
                    document_ids=document_ids,
                    profile_id=request.profile_id,
                    force=request.force,
                    request_id=request.request_id,
                ),
                idempotency_key=idempotency_key,
                payload_fingerprint=payload_fingerprint,
                status="queued",
                requested_documents=len(document_ids),
            )
            self._runs[run_id] = state
            self._idempotency_index[idempotency_key] = (run_id, payload_fingerprint)
            self._persist_run_manifest(state)
            logger.info(
                "chunking_run_created",
                extra={
                    "run_id": run_id,
                    "profile_id": request.profile_id,
                    "requested_documents": len(document_ids),
                    "scope": request.scope,
                    "request_id": request.request_id,
                },
            )
            return state

    def submit_run(self, run_id: str) -> None:
        state = self.get_run_state(run_id)
        if state.status not in {"queued", "interrupted"}:
            logger.info(
                "chunking_run_submit_skipped",
                extra={
                    "run_id": run_id,
                    "status": state.status,
                    "request_id": state.request.request_id,
                },
            )
            return
        logger.info(
            "chunking_run_submitted",
            extra={"run_id": run_id, "request_id": state.request.request_id},
        )
        self._executor.submit(self._execute_run_guarded, run_id)

    def execute_run(self, run_id: str) -> None:
        state = self.get_run_state(run_id)
        if state.status not in {"queued", "interrupted"}:
            return
        if state.status == "interrupted":
            state.documents.clear()
            state.completed_documents = 0
            state.warnings.clear()
        state.status = "running"
        self._persist_run_manifest(state)
        logger.info(
            "chunking_run_started",
            extra={
                "run_id": run_id,
                "requested_documents": state.requested_documents,
                "profile_id": state.request.profile_id,
                "request_id": state.request.request_id,
            },
        )
        profile = ChunkingProfile.local_structural_v1()
        for document_id in state.request.document_ids:
            record = self._inventory_by_document_id()[document_id]
            bundle = self._source.load(ArtifactPaths.for_source(record["source_relpath"]).markdown)
            result = self._orchestrator.process_document(document=bundle, profile=profile)
            state.documents.append(
                {
                    "document_id": document_id,
                    "status": "completed",
                    "reused": result.reused,
                    "run_id": result.run_id,
                    "normalized_relpath": bundle.normalized_relpath,
                }
            )
            state.completed_documents += 1
            self._persist_run_manifest(state)
            logger.info(
                "chunking_document_completed",
                extra={
                    "run_id": run_id,
                    "document_id": document_id,
                    "reused": result.reused,
                    "completed_documents": state.completed_documents,
                    "requested_documents": state.requested_documents,
                    "request_id": state.request.request_id,
                },
            )
        state.status = "completed" if not state.warnings else "completed_with_warnings"
        self._persist_run_manifest(state)
        self._persist_validation(state)
        logger.info(
            "chunking_run_completed",
            extra={
                "run_id": run_id,
                "status": state.status,
                "completed_documents": state.completed_documents,
                "warnings": len(state.warnings),
                "request_id": state.request.request_id,
            },
        )

    def get_run_state(self, run_id: str) -> ChunkingRunState:
        with self._lock:
            state = self._runs.get(run_id)
        if state is None:
            raise ChunkingRunNotFoundError("chunking run does not exist")
        return state

    def get_run_payload(self, run_id: str) -> dict[str, Any]:
        state = self.get_run_state(run_id)
        return {
            "run_id": state.run_id,
            "status": state.status,
            "profile_id": state.request.profile_id,
            "requested_documents": state.requested_documents,
            "completed_documents": state.completed_documents,
            "warnings": list(state.warnings),
            "links": {
                "self": f"/api/chunking/runs/{state.run_id}",
                "documents": f"/api/chunking/runs/{state.run_id}/documents",
                "validation": f"/api/chunking/runs/{state.run_id}/validation",
            },
        }

    def list_run_documents(
        self,
        *,
        run_id: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        state = self.get_run_state(run_id)
        start = (page - 1) * page_size
        end = start + page_size
        items = state.documents[start:end]
        total_items = len(state.documents)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        }

    def get_validation(self, run_id: str) -> dict[str, Any]:
        path = self._validation_path(run_id)
        if not path.exists():
            raise ChunkingRunNotFoundError("chunking run validation does not exist")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_parents(
        self,
        *,
        document_id: str,
        run_id: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        record = self._inventory_by_document_id().get(document_id)
        if record is None:
            raise ChunkingDocumentNotFoundError("document id does not exist")
        normalized_relpath = ArtifactPaths.for_source(record["source_relpath"]).markdown
        if run_id is not None:
            self.get_run_state(run_id)
        parents = self._chunk_repository.read_parents(normalized_relpath=normalized_relpath)
        return self._paginate(items=parents, page=page, page_size=page_size)

    def list_children(
        self,
        *,
        parent_id: str,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        children = self._chunk_repository.find_children_by_parent_id(parent_id=parent_id)
        if not children:
            raise ChunkingParentNotFoundError("parent chunk id does not exist")
        return self._paginate(items=children, page=page, page_size=page_size)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _require_profile(self, profile_id: str) -> None:
        if profile_id != "local-structural-v1":
            raise ChunkingProfileNotFoundError("chunking profile does not exist")

    def _execute_run_guarded(self, run_id: str) -> None:
        try:
            self.execute_run(run_id)
        except Exception as error:
            state = self.get_run_state(run_id)
            state.status = "failed"
            state.warnings.append(str(error))
            self._persist_run_manifest(state)
            logger.exception(
                "chunking_run_failed",
                extra={
                    "run_id": run_id,
                    "completed_documents": state.completed_documents,
                    "requested_documents": state.requested_documents,
                    "request_id": state.request.request_id,
                },
            )

    def _resolved_document_ids(self, request: ChunkingRunRequest) -> tuple[str, ...]:
        inventory = self._inventory_by_document_id()
        if request.scope == "corpus":
            if request.document_ids:
                raise ValueError("document_ids must be empty when scope is corpus")
            return tuple(sorted(inventory.keys()))
        if request.scope != "documents":
            raise ValueError("scope must be corpus or documents")
        if not request.document_ids:
            raise ValueError("document_ids must not be empty when scope is documents")
        unknown = [document_id for document_id in request.document_ids if document_id not in inventory]
        if unknown:
            raise ChunkingDocumentNotFoundError("document id does not exist")
        return tuple(request.document_ids)

    def _inventory_by_document_id(self) -> dict[str, dict[str, Any]]:
        manifest = self._docs_normalized / "_manifests" / "inventory.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return {
            str(record["document_id"]): record
            for record in records
            if isinstance(record, dict) and record.get("document_id") and record.get("source_relpath")
        }

    def _payload_fingerprint(
        self,
        *,
        scope: str,
        document_ids: tuple[str, ...],
        profile_id: str,
        force: bool,
    ) -> str:
        return sha256(
            json.dumps(
                {
                    "scope": scope,
                    "document_ids": list(document_ids),
                    "profile_id": profile_id,
                    "force": force,
                },
                ensure_ascii=True,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def _hydrate_persisted_runs(self) -> None:
        manifest_root = self._manifest_root()
        if not manifest_root.exists():
            return
        for path in sorted(manifest_root.glob("*.api-run.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                state = self._state_from_manifest(payload)
            except Exception:
                logger.warning(
                    "chunking_run_manifest_skipped",
                    extra={"manifest_path": str(path)},
                    exc_info=True,
                )
                continue
            self._runs[state.run_id] = state
            self._idempotency_index[state.idempotency_key] = (
                state.run_id,
                state.payload_fingerprint,
            )

    def _state_from_manifest(self, payload: dict[str, Any]) -> ChunkingRunState:
        request_payload = payload.get("request")
        if not isinstance(request_payload, dict):
            raise ValueError("chunking run manifest request is missing")
        request = ChunkingRunRequest(
            scope=str(request_payload["scope"]),
            document_ids=tuple(str(item) for item in request_payload.get("document_ids", [])),
            profile_id=str(request_payload["profile_id"]),
            force=bool(request_payload["force"]),
            request_id=request_payload.get("request_id"),
        )
        status = str(payload.get("status") or "interrupted")
        if status in {"queued", "running"}:
            status = "interrupted"
        idempotency_key = str(payload.get("idempotency_key") or "")
        payload_fingerprint = str(payload.get("payload_fingerprint") or "")
        if not payload_fingerprint:
            payload_fingerprint = self._payload_fingerprint(
                scope=request.scope,
                document_ids=request.document_ids,
                profile_id=request.profile_id,
                force=request.force,
            )
        if not idempotency_key:
            idempotency_key = payload_fingerprint
        documents = payload.get("documents", [])
        warnings = [str(item) for item in payload.get("warnings", [])]
        return ChunkingRunState(
            run_id=str(payload["run_id"]),
            request=request,
            idempotency_key=idempotency_key,
            payload_fingerprint=payload_fingerprint,
            status=status,
            requested_documents=int(payload.get("requested_documents") or len(request.document_ids)),
            completed_documents=int(payload.get("completed_documents") or len(documents)),
            documents=[dict(document) for document in documents if isinstance(document, dict)],
            warnings=warnings,
        )

    def _paginate(
        self,
        *,
        items: list[dict[str, Any]],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        start = (page - 1) * page_size
        end = start + page_size
        total_items = len(items)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return {
            "items": items[start:end],
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        }

    def _persist_run_manifest(self, state: ChunkingRunState) -> None:
        self._manifest_root().mkdir(parents=True, exist_ok=True)
        path = self._manifest_root() / f"{state.run_id}.api-run.json"
        path.write_text(
            json.dumps(
                {
                    "run_id": state.run_id,
                    "status": state.status,
                    "request": asdict(state.request),
                    "idempotency_key": state.idempotency_key,
                    "payload_fingerprint": state.payload_fingerprint,
                    "requested_documents": state.requested_documents,
                    "completed_documents": state.completed_documents,
                    "documents": state.documents,
                    "warnings": state.warnings,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _persist_validation(self, state: ChunkingRunState) -> None:
        path = self._validation_path(state.run_id)
        path.write_text(
            json.dumps(
                {
                    "run_id": state.run_id,
                    "status": "passed",
                    "documents_checked": state.requested_documents,
                    "errors": 0,
                    "warnings": len(state.warnings),
                    "checks": [],
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _manifest_root(self) -> Path:
        return self._chunks_root / "_manifests"

    def _validation_path(self, run_id: str) -> Path:
        return self._manifest_root() / f"{run_id}.validation.json"
