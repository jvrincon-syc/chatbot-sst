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
from rag_platform.domain.artifact_catalog import (
    NormalizedDocumentArtifactRecord,
    RawDocumentArtifactRecord,
)
from rag_platform.domain.models import (
    ChunkingProfile,
    CorpusSnapshot,
    DocumentProcessingProfile,
    NormalizedDocumentArtifact,
    ProjectConfiguration,
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

    def list_all(self) -> tuple[RagProject, ...]:
        """Devuelve todos los proyectos del catálogo con su configuración vigente."""

    def update_metadata(
        self, project_id: PlatformId, *, display_name: str
    ) -> RagProject:
        """Actualiza los metadatos editables (``display_name``); ``project_id`` es inmutable.

        Raises:
            ProjectNotFound: Si el proyecto no está registrado.
        """


@runtime_checkable
class ProjectConfigurationRepository(Protocol):
    """Lectura y escritura de configuraciones **versionadas** de un proyecto.

    Cada versión es inmutable una vez creada; sus ``target_bindings`` se leen por
    ``(project_id, configuration_version, binding_key)`` para no colapsar la
    historia en la versión más reciente (plan Task 3).
    """

    def get_version(
        self, project_id: PlatformId, version: int
    ) -> ProjectConfiguration:
        """Devuelve la configuración exacta de ``version`` o lanza ``ProjectNotFound``."""

    def create_version(
        self, project_id: PlatformId, configuration: ProjectConfiguration
    ) -> ProjectConfiguration:
        """Persiste una configuración versionada nueva y la devuelve."""


@runtime_checkable
class ProcessingProfileRepository(Protocol):
    """Persistencia de perfiles de procesamiento por proyecto."""

    def get(self, processing_profile_id: PlatformId) -> DocumentProcessingProfile:
        """Devuelve el perfil o lanza ``ProcessingProfileNotFound``."""

    def list_for_project(
        self, project_id: PlatformId
    ) -> tuple[DocumentProcessingProfile, ...]:
        """Devuelve los perfiles de procesamiento del proyecto (orden estable)."""


@runtime_checkable
class ChunkingProfileRepository(Protocol):
    """Persistencia de perfiles de chunking por proyecto."""

    def get(self, chunking_profile_id: PlatformId) -> ChunkingProfile:
        """Devuelve el perfil o lanza ``ChunkingProfileNotFound``."""

    def list_for_project(
        self, project_id: PlatformId
    ) -> tuple[ChunkingProfile, ...]:
        """Devuelve los perfiles de chunking del proyecto (orden estable)."""


@runtime_checkable
class RagVariantRepository(Protocol):
    """Persistencia de variantes RAG con unicidad de receta mientras activas."""

    def find_active_by_fingerprint(
        self, project_id: PlatformId, semantic_recipe_fingerprint: str
    ) -> RagVariant | None:
        """Devuelve la variante activa con ese fingerprint, o ``None``."""

    def add(self, variant: RagVariant) -> RagVariant:
        """Inserta una variante o lanza ``DuplicateVariantRecipe``."""

    def get(self, rag_variant_id: PlatformId) -> RagVariant:
        """Devuelve la variante por id o lanza ``RagVariantNotFound``."""

    def list_for_project(self, project_id: PlatformId) -> tuple[RagVariant, ...]:
        """Devuelve las variantes del proyecto en orden estable (por id)."""


@runtime_checkable
class StorageRootsProvider(Protocol):
    """Deriva las raíces de almacenamiento aisladas de un proyecto."""

    def roots_for(self, project_id: PlatformId) -> ProjectStorageRoots:
        """Devuelve las raíces bajo ``data/projects/{project_id}/``."""


@runtime_checkable
class TargetBindingResolver(Protocol):
    """Resuelve y valida allowlist de bindings target **versionada** por proyecto.

    La lectura es por ``(project_id, configuration_version, binding_key)`` (plan
    Task 3/4): la BD ya versiona los bindings, así que un binding solo se resuelve
    contra la versión de configuración exacta que la receta o la release pinnearon.
    Nunca colapsa la historia en la versión más reciente.
    """

    def find_binding(
        self,
        project_id: PlatformId,
        configuration_version: int,
        binding_key: str,
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

    def list_revisions_for_project(
        self, project_id: PlatformId
    ) -> tuple[SourceDocumentRevision, ...]:
        """Devuelve las revisiones del proyecto en orden estable (read-model GUI).

        El orden es determinista (``uploaded_at`` y luego id) para que la lista de
        documentos de la GUI sobreviva a un refresh sin reordenarse.
        """


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

    def list_normalized_revision_ids(
        self, project_id: PlatformId
    ) -> frozenset[str]:
        """Devuelve los ``srev_`` del proyecto que ya tienen normalizado registrado.

        Alimenta el flag ``normalized_registered`` del read-model de documentos sin
        exponer identidad física ni fingerprints: solo la pertenencia por revisión.
        """


@runtime_checkable
class RawArtifactCatalogRepository(Protocol):
    """Persistencia del catálogo físico de bytes raw auditables."""

    def upsert(self, record: RawDocumentArtifactRecord) -> RawDocumentArtifactRecord:
        """Registra el sidecar físico raw por su revisión inmutable."""


@runtime_checkable
class ProjectRawStorage(Protocol):
    """Escribe los bytes originales subidos bajo la raíz ``raw`` del proyecto.

    Es el único puerto de plataforma que persiste bytes en disco: aísla el sistema
    de archivos del caso de uso de upload para que el router siga siendo un
    adaptador HTTP delgado. La implementación valida contención (sin traversal)
    antes de escribir (frontera de confianza).
    """

    def write_raw_bytes(
        self, project: RagProject, source_relpath: str, content: bytes
    ) -> None:
        """Persiste ``content`` en ``{raw_root}/{source_relpath}`` de forma segura.

        Raises:
            UnsafeArtifactPath: Si ``source_relpath`` intenta escapar de la raíz.
        """


@runtime_checkable
class NormalizedArtifactCatalogRepository(Protocol):
    """Persistencia del catálogo físico de sidecars normalizados."""

    def upsert(
        self, record: NormalizedDocumentArtifactRecord
    ) -> NormalizedDocumentArtifactRecord:
        """Registra los sidecars de un normalizado por su identidad física."""


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

    def list_for_project(
        self, project_id: PlatformId
    ) -> tuple[CorpusSnapshot, ...]:
        """Devuelve los snapshots del proyecto en orden estable (read-model GUI)."""
