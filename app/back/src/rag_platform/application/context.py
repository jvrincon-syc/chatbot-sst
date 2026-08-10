"""Puertos de aplicación de la plataforma RAG (Fase 1).

Aquí viven los contratos que la aplicación necesita de la infraestructura: los
repositorios de catálogo y la política de acceso de operador. Ningún puerto
importa FastAPI, PostgreSQL ni SDKs; la dirección de dependencias es
``infraestructura → aplicación → dominio``.

``PlatformAccessPolicy`` es un puerto porque el RBAC multiusuario no existe aún
(invariante §8 del plan): en esta fase el adaptador representa a un operador
interno, pero ningún handler puede tomar ``actor_id`` de un body o header no
autenticado.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_platform.domain.identity import PlatformId, ProjectDocumentContext
from rag_platform.domain.models import (
    ChunkingProfile,
    CorpusSnapshot,
    DocumentProcessingProfile,
    NormalizedDocumentArtifact,
    ProjectIndexingTargetBinding,
    ProjectStorageRoots,
    RagProject,
    RagVariant,
    SourceDocument,
    SourceDocumentRevision,
)


@runtime_checkable
class PlatformAccessPolicy(Protocol):
    """Autoriza a un operador interno a mutar recursos de plataforma."""

    def require_operator(self, *, actor_id: str) -> None:
        """Falla cerrado si ``actor_id`` no es un operador autorizado.

        Raises:
            PlatformAccessDenied: Si el actor no está autorizado.
        """


@runtime_checkable
class ProjectRepository(Protocol):
    """Persistencia del catálogo de proyectos."""

    def exists(self, project_id: PlatformId) -> bool:
        """Devuelve ``True`` si el proyecto ya está registrado."""

    def get(self, project_id: PlatformId) -> RagProject:
        """Devuelve el proyecto o lanza ``ProjectNotFound``."""

    def add(self, project: RagProject) -> RagProject:
        """Inserta un proyecto nuevo o lanza ``ProjectAlreadyExists``."""

    def has_documents(self, project_id: PlatformId) -> bool:
        """Indica si el proyecto ya tiene documentos (``project_id`` inmutable)."""


@runtime_checkable
class ProcessingProfileRepository(Protocol):
    """Persistencia de perfiles de procesamiento por proyecto."""

    def get(self, processing_profile_id: PlatformId) -> DocumentProcessingProfile:
        """Devuelve el perfil o lanza ``ProcessingProfileNotFound``."""


@runtime_checkable
class ChunkingProfileRepository(Protocol):
    """Persistencia de perfiles de chunking por proyecto."""

    def get(self, chunking_profile_id: PlatformId) -> ChunkingProfile:
        """Devuelve el perfil o lanza ``ChunkingProfileNotFound``."""


@runtime_checkable
class RagVariantRepository(Protocol):
    """Persistencia de variantes RAG con unicidad de receta mientras activas."""

    def find_active_by_fingerprint(
        self, project_id: PlatformId, semantic_recipe_fingerprint: str
    ) -> RagVariant | None:
        """Devuelve la variante activa con ese fingerprint, o ``None``."""

    def add(self, variant: RagVariant) -> RagVariant:
        """Inserta una variante o lanza ``DuplicateVariantRecipe``."""


@runtime_checkable
class StorageRootsProvider(Protocol):
    """Deriva las raíces de almacenamiento aisladas de un proyecto."""

    def roots_for(self, project_id: PlatformId) -> ProjectStorageRoots:
        """Devuelve las raíces bajo ``data/projects/{project_id}/``."""


@runtime_checkable
class TargetBindingResolver(Protocol):
    """Resuelve y valida allowlist de bindings target por proyecto."""

    def find_binding(
        self, project_id: PlatformId, binding_key: str
    ) -> ProjectIndexingTargetBinding | None:
        """Devuelve el binding permitido o ``None`` si no está en la allowlist."""


@runtime_checkable
class SourceDocumentRepository(Protocol):
    """Persistencia de documentos lógicos y sus revisiones inmutables (Fase 2)."""

    def find_document(
        self, logical_document_id: PlatformId
    ) -> SourceDocument | None:
        """Devuelve el documento lógico o ``None``."""

    def upsert_document(self, document: SourceDocument) -> SourceDocument:
        """Registra el documento lógico si no existía; idempotente por identidad."""

    def find_revision_by_hash(
        self, logical_document_id: PlatformId, raw_content_hash: str
    ) -> SourceDocumentRevision | None:
        """Devuelve la revisión con ese hash de raw, o ``None`` (idempotencia)."""

    def get_revision(
        self, source_document_revision_id: PlatformId
    ) -> SourceDocumentRevision:
        """Devuelve la revisión o lanza ``SourceDocumentRevisionNotFound``."""

    def add_revision(
        self, revision: SourceDocumentRevision
    ) -> SourceDocumentRevision:
        """Inserta una revisión inmutable nueva; nunca sobreescribe la anterior."""


@runtime_checkable
class NormalizedArtifactRepository(Protocol):
    """Persistencia de normalizados por identidad exacta (Fase 2)."""

    def find(
        self,
        *,
        project_id: PlatformId,
        source_document_revision_id: PlatformId,
        processing_profile_fingerprint: str,
    ) -> NormalizedDocumentArtifact | None:
        """Devuelve el normalizado con la identidad exacta, o ``None``."""

    def add(
        self, artifact: NormalizedDocumentArtifact
    ) -> NormalizedDocumentArtifact:
        """Registra un normalizado recién construido."""


@runtime_checkable
class NormalizedArtifactBuilder(Protocol):
    """Puerto que construye un normalizado ausente.

    La plataforma no reimplementa el motor de ingesta (invariante del plan); este
    puerto se inyecta con un adaptador que orquesta las etapas existentes.
    """

    def build(
        self, context: ProjectDocumentContext
    ) -> NormalizedDocumentArtifact:
        """Construye y devuelve el normalizado para el contexto dado."""


@runtime_checkable
class CorpusSnapshotRepository(Protocol):
    """Persistencia de corpus snapshots inmutables (Fase 2)."""

    def find_by_manifest(
        self, project_id: PlatformId, manifest_hash: str
    ) -> CorpusSnapshot | None:
        """Devuelve el snapshot con ese ``manifest_hash``, o ``None`` (idempotencia)."""

    def add(self, snapshot: CorpusSnapshot) -> CorpusSnapshot:
        """Inserta un corpus snapshot inmutable."""
