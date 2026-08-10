"""Application ports for embedding engines, repositories and artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from embedding.domain.models import (
    ChunkBundleRef,
    CompatibilityReport,
    EmbeddingBundle,
    EmbeddingBundleChunk,
    EmbeddingProfile,
    EmbeddingRun,
    EmbeddingRuntimeStatus,
    Normalization,
    ReadinessCheck,
)


class EmbeddingEngine(Protocol):
    """A concrete embedding runtime bound to one durable profile."""

    @property
    def provider_name(self) -> str:
        """Return the provider name the engine implements."""

    @property
    def model_name(self) -> str:
        """Return the model the engine loaded."""

    @property
    def dimension(self) -> int:
        """Return the dense vector dimension produced by the engine."""

    @property
    def normalization(self) -> Normalization:
        """Return the normalization the engine applies to its vectors."""

    @property
    def supports_queries(self) -> bool:
        """Return whether the engine can embed queries."""

    def observe_revision(self) -> str:
        """Return the runtime-observable model revision, or ``unknown_revision``."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one document vector per input text."""

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one query vector per input text."""


class EmbeddingEngineRegistry(Protocol):
    """Resolve engines by exact durable profile, never by first available."""

    def resolve_document_engine(self, profile: EmbeddingProfile) -> EmbeddingEngine:
        """Return the engine allowed to embed documents for this profile."""

    def resolve_query_engine(self, profile: EmbeddingProfile) -> EmbeddingEngine:
        """Return the engine allowed to embed queries for this profile."""

    def get_runtime_status(self, profile: EmbeddingProfile) -> EmbeddingRuntimeStatus:
        """Return operational availability without raising."""

    def validate_engine_compatibility(
        self,
        profile: EmbeddingProfile,
        engine: EmbeddingEngine,
    ) -> CompatibilityReport:
        """Compare every semantic field of the profile against the engine."""


class EmbeddingProfileRepository(Protocol):
    """Durable read/write access to ``indexing_profiles``."""

    def get(self, profile_id: str) -> EmbeddingProfile:
        """Return one profile or raise ``EmbeddingProfileNotFound``."""

    def list_profiles(self) -> list[EmbeddingProfile]:
        """Return every registered profile, including blocked ones."""

    def mark_verified(
        self,
        *,
        profile_id: str,
        configuration_fingerprint: str,
        model_revision: str,
        document_enabled: bool,
        query_enabled: bool,
    ) -> EmbeddingProfile:
        """Promote one profile after an explicit compatibility verification."""


class ChunkBundleRepository(Protocol):
    """Durable read/write access to ``chunk_bundles``."""

    def get(self, chunk_bundle_id: str) -> ChunkBundleRef:
        """Return one registered chunk bundle or raise ``ChunkBundleNotFound``."""

    def list_bundles(self) -> list[ChunkBundleRef]:
        """Return every registered chunk bundle."""

    def ensure_registered(self, bundle: ChunkBundleRef) -> ChunkBundleRef:
        """Persist one chunk bundle identity so downstream FKs can reference it."""


class EmbeddingRunRepository(Protocol):
    """Durable read/write access to ``embedding_runs``."""

    def create(self, run: EmbeddingRun) -> EmbeddingRun:
        """Insert a run, returning the stored row."""

    def get(self, embedding_run_id: str) -> EmbeddingRun:
        """Return one run or raise ``EmbeddingRunNotFound``."""

    def find_by_idempotency_key(self, idempotency_key: str) -> EmbeddingRun | None:
        """Return the run already stored under one idempotency key."""

    def list_runs(self) -> list[EmbeddingRun]:
        """Return every run, newest first."""

    def claim(self, embedding_run_id: str) -> bool:
        """Transition ``pending`` to ``running`` exactly once.

        Returns:
            ``True`` when this caller won the claim.
        """

    def update(self, run: EmbeddingRun) -> EmbeddingRun:
        """Persist a durable state transition for one run."""

    def reconcile_interrupted(self) -> list[str]:
        """Fail runs left ``running`` by a process that never finished."""


class EmbeddingBundleRepository(Protocol):
    """Durable read/write access to ``embedding_bundles``."""

    def upsert(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Insert or update an unsealed bundle."""

    def seal(self, bundle: EmbeddingBundle) -> EmbeddingBundle:
        """Persist the sealed bundle; refuses to overwrite a sealed row."""

    def get(self, embedding_bundle_id: str) -> EmbeddingBundle:
        """Return one bundle or raise ``EmbeddingBundleNotFound``."""

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

    def replace_chunks(
        self,
        *,
        embedding_bundle_id: str,
        chunks: Sequence[EmbeddingBundleChunk],
    ) -> int:
        """Replace the chunk map rows of one unsealed bundle."""

    def list_chunks(self, embedding_bundle_id: str) -> list[EmbeddingBundleChunk]:
        """Return the durable chunk map, ordered by ``chunk_ordinal``."""

    def set_readiness_status(
        self,
        *,
        embedding_bundle_id: str,
        readiness_status: str,
    ) -> EmbeddingBundle:
        """Update the operational readiness projection of a sealed bundle.

        Sealing freezes semantics, artifacts and validation. ``readiness_status``
        stays mutable because activation and rollback move it.
        """


class ReadinessCheckRepository(Protocol):
    """Durable write access to ``readiness_checks``."""

    def record(self, check: ReadinessCheck) -> ReadinessCheck:
        """Persist one readiness check idempotently."""

    def latest(
        self,
        *,
        check_kind: str,
        subject_id: str,
    ) -> ReadinessCheck | None:
        """Return the most recent check for one subject."""


class EmbeddingBundleArtifactStore(Protocol):
    """Atomic filesystem store for vector artifacts and chunk maps."""

    def stage(
        self,
        *,
        embedding_bundle_id: str,
        manifest: dict[str, object],
        vectors: Sequence[Sequence[float]],
        chunk_map: Sequence[dict[str, object]],
    ) -> "ArtifactRefs":
        """Write artifacts into an isolated staging directory."""

    def promote(self, *, embedding_bundle_id: str) -> "ArtifactRefs":
        """Atomically publish staged artifacts; never overwrites a sealed bundle."""

    def load_vectors(self, *, vector_artifact_relpath: str) -> list[list[float]]:
        """Read back the dense vectors of a published bundle."""

    def read_manifest(self, *, embedding_bundle_id: str) -> dict[str, object]:
        """Read the published manifest of one bundle."""


class ArtifactRefs(Protocol):
    """Relative artifact locations plus their checksums."""

    @property
    def vector_artifact_relpath(self) -> str:
        """Return the vector artifact path, relative to the artifact root."""

    @property
    def chunk_map_relpath(self) -> str:
        """Return the chunk map path, relative to the artifact root."""

    @property
    def manifest_relpath(self) -> str:
        """Return the manifest path, relative to the artifact root."""

    @property
    def checksums(self) -> dict[str, str]:
        """Return sha256 checksums keyed by artifact file name."""

    @property
    def dtype(self) -> str:
        """Return the stored numpy dtype name."""

    @property
    def shape(self) -> str:
        """Return the stored vector shape as ``"rows x columns"``."""
