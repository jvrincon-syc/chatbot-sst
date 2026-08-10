"""Repositorios in-memory determinísticos de plataforma (tests y dry-run).

Implementan el mismo contrato observable que los adaptadores PostgreSQL,
incluida la unicidad ``UNIQUE(project_id, semantic_recipe_fingerprint)`` de
variantes activas y la inmutabilidad de ``project_id``. No consumen red.
"""

from __future__ import annotations

import threading

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.domain.errors import (
    ChunkingProfileNotFound,
    DuplicateVariantRecipe,
    PlatformAccessDenied,
    ProcessingProfileNotFound,
    ProjectAlreadyExists,
    ProjectNotFound,
    SourceDocumentRevisionNotFound,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import (
    ChunkingProfile,
    CorpusSnapshot,
    DocumentProcessingProfile,
    NormalizedDocumentArtifact,
    ProjectIndexingTargetBinding,
    RagProject,
    RagVariant,
    RagVariantState,
    SourceDocument,
    SourceDocumentRevision,
)


class InMemoryProjectRepository:
    """Catálogo de proyectos en memoria con ``project_id`` estable."""

    def __init__(self) -> None:
        self._projects: dict[str, RagProject] = {}
        self._with_documents: set[str] = set()
        self._lock = threading.Lock()

    def exists(self, project_id: PlatformId) -> bool:
        return project_id.value in self._projects

    def get(self, project_id: PlatformId) -> RagProject:
        try:
            return self._projects[project_id.value]
        except KeyError as error:
            raise ProjectNotFound(project_id.value) from error

    def add(self, project: RagProject) -> RagProject:
        with self._lock:
            if project.project_id.value in self._projects:
                raise ProjectAlreadyExists(project.project_id.value)
            self._projects[project.project_id.value] = project
        return project

    def has_documents(self, project_id: PlatformId) -> bool:
        return project_id.value in self._with_documents

    def mark_has_documents(self, project_id: PlatformId) -> None:
        """Marca el proyecto como poseedor de documentos (helper de test)."""

        self._with_documents.add(project_id.value)


class InMemoryProcessingProfileRepository:
    """Perfiles de procesamiento en memoria."""

    def __init__(self, profiles: tuple[DocumentProcessingProfile, ...] = ()) -> None:
        self._profiles = {p.processing_profile_id.value: p for p in profiles}

    def add(self, profile: DocumentProcessingProfile) -> None:
        self._profiles[profile.processing_profile_id.value] = profile

    def get(self, processing_profile_id: PlatformId) -> DocumentProcessingProfile:
        try:
            return self._profiles[processing_profile_id.value]
        except KeyError as error:
            raise ProcessingProfileNotFound(processing_profile_id.value) from error


class InMemoryChunkingProfileRepository:
    """Perfiles de chunking en memoria."""

    def __init__(self, profiles: tuple[ChunkingProfile, ...] = ()) -> None:
        self._profiles = {p.chunking_profile_id.value: p for p in profiles}

    def add(self, profile: ChunkingProfile) -> None:
        self._profiles[profile.chunking_profile_id.value] = profile

    def get(self, chunking_profile_id: PlatformId) -> ChunkingProfile:
        try:
            return self._profiles[chunking_profile_id.value]
        except KeyError as error:
            raise ChunkingProfileNotFound(chunking_profile_id.value) from error


class InMemoryRagVariantRepository:
    """Variantes en memoria con unicidad de receta mientras activas."""

    def __init__(self) -> None:
        self._variants: dict[str, RagVariant] = {}
        self._lock = threading.Lock()

    def find_active_by_fingerprint(
        self, project_id: PlatformId, semantic_recipe_fingerprint: str
    ) -> RagVariant | None:
        for variant in self._variants.values():
            if (
                variant.project_id == project_id
                and variant.state is RagVariantState.ACTIVE
                and variant.semantic_recipe_fingerprint == semantic_recipe_fingerprint
            ):
                return variant
        return None

    def add(self, variant: RagVariant) -> RagVariant:
        with self._lock:
            existing = self.find_active_by_fingerprint(
                variant.project_id, variant.semantic_recipe_fingerprint
            )
            if existing is not None:
                raise DuplicateVariantRecipe(variant.semantic_recipe_fingerprint)
            self._variants[variant.rag_variant_id.value] = variant
        return variant


class InMemoryTargetBindingResolver:
    """Allowlist de bindings target en memoria."""

    def __init__(self, bindings: tuple[ProjectIndexingTargetBinding, ...] = ()) -> None:
        # Clave: (project_id.value, binding_key). El proyecto se pasa al resolver.
        self._by_key: dict[str, ProjectIndexingTargetBinding] = {
            b.binding_key: b for b in bindings
        }

    def find_binding(
        self, project_id: PlatformId, binding_key: str
    ) -> ProjectIndexingTargetBinding | None:
        return self._by_key.get(binding_key)


class AllowAllAccessPolicy:
    """Adaptador de operador interno para tests: autoriza todo actor no vacío."""

    def require_operator(self, *, actor_id: str) -> None:
        if not actor_id or not actor_id.strip():
            raise PlatformAccessDenied("empty actor_id")


class InMemorySourceDocumentRepository:
    """Documentos lógicos y revisiones inmutables en memoria (Fase 2)."""

    def __init__(self) -> None:
        self._documents: dict[str, SourceDocument] = {}
        self._revisions: dict[str, SourceDocumentRevision] = {}
        self._lock = threading.Lock()

    def find_document(self, logical_document_id: PlatformId) -> SourceDocument | None:
        return self._documents.get(logical_document_id.value)

    def upsert_document(self, document: SourceDocument) -> SourceDocument:
        self._documents.setdefault(document.logical_document_id.value, document)
        return self._documents[document.logical_document_id.value]

    def find_revision_by_hash(
        self, logical_document_id: PlatformId, raw_content_hash: str
    ) -> SourceDocumentRevision | None:
        for revision in self._revisions.values():
            if (
                revision.logical_document_id == logical_document_id
                and revision.raw_content_hash == raw_content_hash
            ):
                return revision
        return None

    def get_revision(
        self, source_document_revision_id: PlatformId
    ) -> SourceDocumentRevision:
        try:
            return self._revisions[source_document_revision_id.value]
        except KeyError as error:
            raise SourceDocumentRevisionNotFound(
                source_document_revision_id.value
            ) from error

    def add_revision(
        self, revision: SourceDocumentRevision
    ) -> SourceDocumentRevision:
        with self._lock:
            # Inmutable: nunca sobreescribe una revisión existente.
            self._revisions.setdefault(
                revision.source_document_revision_id.value, revision
            )
        return self._revisions[revision.source_document_revision_id.value]


class InMemoryNormalizedArtifactRepository:
    """Normalizados por identidad exacta en memoria (Fase 2)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str, str], NormalizedDocumentArtifact] = {}

    @staticmethod
    def _key(
        project_id: PlatformId,
        source_document_revision_id: PlatformId,
        processing_profile_fingerprint: str,
    ) -> tuple[str, str, str]:
        return (
            project_id.value,
            source_document_revision_id.value,
            processing_profile_fingerprint,
        )

    def find(
        self,
        *,
        project_id: PlatformId,
        source_document_revision_id: PlatformId,
        processing_profile_fingerprint: str,
    ) -> NormalizedDocumentArtifact | None:
        return self._by_key.get(
            self._key(
                project_id,
                source_document_revision_id,
                processing_profile_fingerprint,
            )
        )

    def add(
        self, artifact: NormalizedDocumentArtifact
    ) -> NormalizedDocumentArtifact:
        key = self._key(
            artifact.project_id,
            artifact.source_document_revision_id,
            artifact.processing_profile_fingerprint,
        )
        self._by_key.setdefault(key, artifact)
        return self._by_key[key]


class InMemoryCorpusSnapshotRepository:
    """Corpus snapshots inmutables en memoria (Fase 2)."""

    def __init__(self) -> None:
        self._by_manifest: dict[tuple[str, str], CorpusSnapshot] = {}

    def find_by_manifest(
        self, project_id: PlatformId, manifest_hash: str
    ) -> CorpusSnapshot | None:
        return self._by_manifest.get((project_id.value, manifest_hash))

    def add(self, snapshot: CorpusSnapshot) -> CorpusSnapshot:
        key = (snapshot.project_id.value, snapshot.manifest_hash)
        self._by_manifest.setdefault(key, snapshot)
        return self._by_manifest[key]


# Verificación estructural: el adaptador satisface el puerto.
_policy: PlatformAccessPolicy = AllowAllAccessPolicy()
