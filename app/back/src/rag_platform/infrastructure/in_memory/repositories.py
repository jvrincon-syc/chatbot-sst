"""Repositorios in-memory determinísticos de plataforma (tests y dry-run).

Implementan el mismo contrato observable que los adaptadores PostgreSQL,
incluida la unicidad ``UNIQUE(project_id, semantic_recipe_fingerprint)`` de
variantes activas y la inmutabilidad de ``project_id``. No consumen red.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import uuid

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.domain.errors import (
    BuildStepNotFound,
    ChunkingProfileNotFound,
    DuplicateVariantRecipe,
    MaterializationSealed,
    PlatformAccessDenied,
    ProcessingProfileNotFound,
    ProjectAlreadyExists,
    ProjectNotFound,
    SourceDocumentRevisionNotFound,
)
from rag_platform.domain.identity import IdentityKind, PlatformId, RagBuildContext
from rag_platform.domain.models import (
    BuildOutcome,
    BuildStage,
    ChunkingProfile,
    CorpusSnapshot,
    DocumentProcessingProfile,
    IndexingMaterialization,
    MaterializationStatus,
    NormalizedDocumentArtifact,
    ProjectConfiguration,
    ProjectIndexingTargetBinding,
    RagBuildStep,
    RagProject,
    RagVariant,
    RagVariantState,
    ReuseKind,
    SealedEmbeddingBundle,
    SourceDocument,
    SourceDocumentRevision,
)
from embedding.domain.models import ChunkBundleRef


class InMemoryProjectRepository:
    """Catálogo de proyectos en memoria con ``project_id`` estable.

    Además de ``ProjectRepository`` satisface ``ProjectConfigurationRepository``:
    guarda las configuraciones **por versión** para que una lectura histórica no
    colapse en la última. ``get`` devuelve el proyecto con su configuración
    vigente (versión máxima), de modo que una edición posterior sea visible.
    """

    def __init__(self) -> None:
        self._projects: dict[str, RagProject] = {}
        self._configurations: dict[str, dict[int, ProjectConfiguration]] = {}
        self._with_documents: set[str] = set()
        self._lock = threading.Lock()

    def exists(self, project_id: PlatformId) -> bool:
        return project_id.value in self._projects

    def get(self, project_id: PlatformId) -> RagProject:
        try:
            project = self._projects[project_id.value]
        except KeyError as error:
            raise ProjectNotFound(project_id.value) from error
        return project.model_copy(
            update={"configuration": self._current_configuration(project_id.value)}
        )

    def add(self, project: RagProject) -> RagProject:
        with self._lock:
            if project.project_id.value in self._projects:
                raise ProjectAlreadyExists(project.project_id.value)
            self._projects[project.project_id.value] = project
            self._configurations[project.project_id.value] = {
                project.configuration.version: project.configuration
            }
        return project

    def list_all(self) -> tuple[RagProject, ...]:
        with self._lock:
            ids = tuple(self._projects.keys())
        return tuple(
            self.get(PlatformId(kind=IdentityKind.PROJECT, value=pid)) for pid in ids
        )

    def update_metadata(
        self, project_id: PlatformId, *, display_name: str
    ) -> RagProject:
        with self._lock:
            current = self._projects.get(project_id.value)
            if current is None:
                raise ProjectNotFound(project_id.value)
            updated = current.model_copy(update={"display_name": display_name})
            self._projects[project_id.value] = updated
        return self.get(project_id)

    def get_version(
        self, project_id: PlatformId, version: int
    ) -> ProjectConfiguration:
        try:
            return self._configurations[project_id.value][version]
        except KeyError as error:
            raise ProjectNotFound(project_id.value) from error

    def create_version(
        self, project_id: PlatformId, configuration: ProjectConfiguration
    ) -> ProjectConfiguration:
        with self._lock:
            if project_id.value not in self._projects:
                raise ProjectNotFound(project_id.value)
            self._configurations[project_id.value][configuration.version] = (
                configuration
            )
        return configuration

    def _current_configuration(self, project_id_value: str) -> ProjectConfiguration:
        versions = self._configurations[project_id_value]
        return versions[max(versions)]

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

    def list_for_project(
        self, project_id: PlatformId
    ) -> tuple[DocumentProcessingProfile, ...]:
        return tuple(
            profile
            for _, profile in sorted(self._profiles.items())
            if profile.project_id == project_id
        )


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

    def list_for_project(
        self, project_id: PlatformId
    ) -> tuple[ChunkingProfile, ...]:
        return tuple(
            profile
            for _, profile in sorted(self._profiles.items())
            if profile.project_id == project_id
        )


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

    def list_for_project(self, project_id: PlatformId) -> tuple[RagVariant, ...]:
        return tuple(
            variant
            for _, variant in sorted(self._variants.items())
            if variant.project_id == project_id
        )


class InMemoryTargetBindingResolver:
    """Allowlist de bindings target **versionada** en memoria.

    Espeja el esquema versionado ``PK(project_id, configuration_version,
    binding_key)``: la clave incluye la versión, de modo que dos versiones de
    configuración pueden mapear el mismo ``binding_key`` a targets distintos sin
    colapsar la historia. Por compatibilidad con los tests existentes, los
    bindings pasados al constructor se registran bajo ``configuration_version``
    (por defecto 1).
    """

    def __init__(
        self,
        bindings: tuple[ProjectIndexingTargetBinding, ...] = (),
        *,
        configuration_version: int = 1,
    ) -> None:
        self._by_key: dict[tuple[int, str], ProjectIndexingTargetBinding] = {}
        for binding in bindings:
            self._by_key[(configuration_version, binding.binding_key)] = binding

    def add_binding(
        self, *, configuration_version: int, binding: ProjectIndexingTargetBinding
    ) -> None:
        """Registra un binding bajo una versión de configuración (helper de test)."""

        self._by_key[(configuration_version, binding.binding_key)] = binding

    def find_binding(
        self,
        project_id: PlatformId,
        configuration_version: int,
        binding_key: str,
    ) -> ProjectIndexingTargetBinding | None:
        return self._by_key.get((configuration_version, binding_key))


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


class InMemoryChunkBundleReuseRepository:
    """Chunk bundles sellados indexados por identidad física exacta (Fase 3).

    La clave incluye ``project_id``: dos proyectos con bytes idénticos nunca
    comparten entrada, de modo que el reuso entre proyectos es imposible por
    construcción (fail-closed).
    """

    def __init__(self) -> None:
        self._by_identity: dict[tuple[str, str, str, str], ChunkBundleRef] = {}

    @staticmethod
    def _key(
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> tuple[str, str, str, str]:
        return (
            project_id.value,
            normalized_document_id,
            chunking_profile_fingerprint,
            bundle_schema_version,
        )

    def register_sealed(
        self,
        bundle: ChunkBundleRef,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef:
        """Registra un bundle sellado; idempotente por identidad física."""

        key = self._key(
            project_id,
            normalized_document_id,
            chunking_profile_fingerprint,
            bundle_schema_version,
        )
        self._by_identity.setdefault(key, bundle)
        return self._by_identity[key]

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        normalized_document_id: str,
        chunking_profile_fingerprint: str,
        bundle_schema_version: str,
    ) -> ChunkBundleRef | None:
        return self._by_identity.get(
            self._key(
                project_id,
                normalized_document_id,
                chunking_profile_fingerprint,
                bundle_schema_version,
            )
        )


class InMemoryRagBuildRunRepository:
    """Ledger de runs y pasos de build en memoria (Fase 3)."""

    def __init__(self) -> None:
        self._steps: dict[str, RagBuildStep] = {}
        self._runs: dict[str, tuple[PlatformId, PlatformId]] = {}
        self._lock = threading.Lock()

    def start_step(
        self, *, context: RagBuildContext, stage: BuildStage
    ) -> RagBuildStep:
        run_id = f"rbr_{context.rag_release_id.value}"
        step_id = f"rbs_{uuid.uuid4().hex}"
        with self._lock:
            self._runs.setdefault(
                run_id, (context.rag_release_id, context.project_id)
            )
            step = RagBuildStep(
                step_id=step_id,
                rag_build_run_id=run_id,
                rag_release_id=context.rag_release_id,
                project_id=context.project_id,
                stage=stage,
                started_at=datetime.now(timezone.utc),
            )
            self._steps[step_id] = step
        return step

    def complete_step(
        self,
        *,
        step_id: str,
        outcome: BuildOutcome,
        reuse_kind: ReuseKind | None = None,
        source_artifact_id: str | None = None,
    ) -> RagBuildStep:
        with self._lock:
            current = self._steps.get(step_id)
            if current is None:
                raise BuildStepNotFound(step_id)
            completed = current.model_copy(
                update={
                    "outcome": outcome,
                    "reuse_kind": reuse_kind,
                    "source_artifact_id": source_artifact_id,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            self._steps[step_id] = completed
        return completed

    def steps_for(self, rag_release_id: PlatformId) -> tuple[RagBuildStep, ...]:
        """Devuelve los pasos registrados para una release (ayuda de test)."""

        with self._lock:
            steps = tuple(self._steps.values())
        return tuple(
            step for step in steps if step.rag_release_id == rag_release_id
        )


class InMemorySealedEmbeddingBundleRepository:
    """Embedding bundles sellados indexados por identidad física exacta (Fase 4).

    La clave incluye ``project_id``: dos proyectos con bytes idénticos nunca comparten
    entrada, de modo que el reuso entre proyectos es imposible por construcción.
    """

    def __init__(self) -> None:
        self._by_identity: dict[tuple[str, str, str, str], SealedEmbeddingBundle] = {}

    @staticmethod
    def _key(
        project_id: PlatformId,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
    ) -> tuple[str, str, str, str]:
        return (
            project_id.value,
            source_chunk_bundle_id,
            embedding_profile_id,
            configuration_fingerprint,
        )

    def register_sealed(
        self,
        bundle: SealedEmbeddingBundle,
        *,
        embedding_profile_id: str,
        configuration_fingerprint: str,
    ) -> SealedEmbeddingBundle:
        """Registra un bundle sellado; idempotente por identidad física."""

        key = self._key(
            bundle.project_id,
            bundle.source_chunk_bundle_id,
            embedding_profile_id,
            configuration_fingerprint,
        )
        self._by_identity.setdefault(key, bundle)
        return self._by_identity[key]

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        source_chunk_bundle_id: str,
        embedding_profile_id: str,
        configuration_fingerprint: str,
    ) -> SealedEmbeddingBundle | None:
        return self._by_identity.get(
            self._key(
                project_id,
                source_chunk_bundle_id,
                embedding_profile_id,
                configuration_fingerprint,
            )
        )


class InMemoryIndexingMaterializationRepository:
    """Lifecycle inmutable ``WRITING → SEALED | FAILED`` en memoria (Fase 4).

    Reproduce el contrato observable del adaptador Postgres: ``begin_writing`` se
    niega a reabrir una fila ``SEALED``; ``seal``/``mark_failed`` solo actúan sobre
    ``WRITING``; ``find_sealed`` solo devuelve filas selladas.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, IndexingMaterialization] = {}
        self._by_identity: dict[tuple[str, str, str, str], str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _identity(
        materialization: IndexingMaterialization,
    ) -> tuple[str, str, str, str]:
        return (
            materialization.project_id.value,
            materialization.embedding_bundle_id,
            materialization.indexing_target_id,
            materialization.storage_schema_version,
        )

    def find_sealed(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization | None:
        key = (
            project_id.value,
            embedding_bundle_id,
            indexing_target_id,
            storage_schema_version,
        )
        with self._lock:
            materialization_id = self._by_identity.get(key)
            if materialization_id is None:
                return None
            current = self._by_id[materialization_id]
        return current if current.status is MaterializationStatus.SEALED else None

    def begin_writing(
        self,
        *,
        project_id: PlatformId,
        embedding_bundle_id: str,
        indexing_target_id: str,
        storage_schema_version: str,
    ) -> IndexingMaterialization:
        key = (
            project_id.value,
            embedding_bundle_id,
            indexing_target_id,
            storage_schema_version,
        )
        with self._lock:
            existing_id = self._by_identity.get(key)
            if existing_id is not None:
                existing = self._by_id[existing_id]
                if existing.status is MaterializationStatus.SEALED:
                    raise MaterializationSealed(
                        "materialization is already sealed and cannot be reopened"
                    )
            materialization = IndexingMaterialization(
                materialization_id=f"mat_{uuid.uuid4().hex}",
                project_id=project_id,
                embedding_bundle_id=embedding_bundle_id,
                indexing_target_id=indexing_target_id,
                storage_schema_version=storage_schema_version,
                status=MaterializationStatus.WRITING,
                started_at=datetime.now(timezone.utc),
            )
            self._by_id[materialization.materialization_id] = materialization
            self._by_identity[key] = materialization.materialization_id
        return materialization

    def seal(
        self,
        *,
        materialization_id: str,
        canonical_checksum: str,
        parent_node_count: int,
        child_node_count: int,
        vector_count: int,
    ) -> IndexingMaterialization:
        with self._lock:
            current = self._require_writing(materialization_id)
            sealed = current.model_copy(
                update={
                    "status": MaterializationStatus.SEALED,
                    "canonical_checksum": canonical_checksum,
                    "parent_node_count": parent_node_count,
                    "child_node_count": child_node_count,
                    "vector_count": vector_count,
                    "sealed_at": datetime.now(timezone.utc),
                }
            )
            self._by_id[materialization_id] = sealed
        return sealed

    def mark_failed(
        self, *, materialization_id: str, failure_code: str
    ) -> IndexingMaterialization:
        with self._lock:
            current = self._require_writing(materialization_id)
            failed = current.model_copy(
                update={
                    "status": MaterializationStatus.FAILED,
                    "failed_at": datetime.now(timezone.utc),
                    "failure_code": failure_code,
                }
            )
            self._by_id[materialization_id] = failed
        return failed

    def _require_writing(self, materialization_id: str) -> IndexingMaterialization:
        current = self._by_id.get(materialization_id)
        if current is None or current.status is not MaterializationStatus.WRITING:
            raise MaterializationSealed(
                f"materialization {materialization_id!r} is not in WRITING state"
            )
        return current


# Verificación estructural: el adaptador satisface el puerto.
_policy: PlatformAccessPolicy = AllowAllAccessPolicy()
