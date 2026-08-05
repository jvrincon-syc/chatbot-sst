from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from typing import Protocol

from chunking.application.ports import (
    ChunkBundleRepositoryPort,
    StoredChunkBundleMetadata,
    StructuralChunkerPort,
)
from chunking.domain.models import ChunkBundle, ChunkingProfile, NormalizedDocumentBundle


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkingValidationReport:
    """Minimal fail-closed validation summary for one persisted bundle."""

    document_id: str
    parent_count: int
    child_count: int
    status: str


@dataclass(frozen=True)
class ChunkingRunResult:
    """Traceable chunking execution result for one normalized document."""

    run_id: str
    document_id: str
    reused: bool
    bundle_fingerprint: str
    profile_fingerprint: str
    validation: ChunkingValidationReport


class RunRepositoryPort(Protocol):
    """Persists run-level manifests and validation reports."""

    def record(
        self,
        *,
        result: ChunkingRunResult,
        metadata: StoredChunkBundleMetadata,
    ) -> None:
        """Persist one run manifest and its validation report."""


@dataclass(frozen=True)
class ChunkingOrchestrator:
    """Coordinates local chunking, idempotence, and durable persistence."""

    engine: StructuralChunkerPort
    bundle_repository: ChunkBundleRepositoryPort
    run_repository: RunRepositoryPort

    def process_document(
        self,
        *,
        document: NormalizedDocumentBundle,
        profile: ChunkingProfile,
    ) -> ChunkingRunResult:
        bundle = self.engine.chunk(document, profile)
        existing = self.bundle_repository.read_metadata(document=document)
        if (
            existing is not None
            and existing.bundle_fingerprint == bundle.fingerprint
            and existing.profile_fingerprint == profile.fingerprint
        ):
            result = self._result_from_bundle(
                document=document,
                bundle=bundle,
                reused=True,
            )
            self.run_repository.record(result=result, metadata=existing)
            logger.info(
                "Reused persisted chunk bundle",
                extra={
                    "document_id": document.document_id,
                    "run_id": result.run_id,
                    "profile_id": profile.profile_id,
                },
            )
            return result

        stored = self.bundle_repository.replace(document=document, bundle=bundle)
        result = self._result_from_bundle(
            document=document,
            bundle=bundle,
            reused=False,
        )
        self.run_repository.record(result=result, metadata=stored)
        logger.info(
            "Persisted chunk bundle",
            extra={
                "document_id": document.document_id,
                "run_id": result.run_id,
                "profile_id": profile.profile_id,
                "reused": False,
            },
        )
        return result

    def _result_from_bundle(
        self,
        *,
        document: NormalizedDocumentBundle,
        bundle: ChunkBundle,
        reused: bool,
    ) -> ChunkingRunResult:
        validation = ChunkingValidationReport(
            document_id=document.document_id,
            parent_count=len(bundle.parents),
            child_count=len(bundle.children),
            status="passed",
        )
        run_id = sha256(
            "|".join(
                (
                    document.document_id,
                    document.source_hash,
                    document.corpus_version,
                    bundle.profile.fingerprint,
                    bundle.fingerprint,
                )
            ).encode("utf-8")
        ).hexdigest()
        return ChunkingRunResult(
            run_id=run_id,
            document_id=document.document_id,
            reused=reused,
            bundle_fingerprint=bundle.fingerprint,
            profile_fingerprint=bundle.profile.fingerprint,
            validation=validation,
        )
