"""Schemas HTTP de la plataforma RAG (Fase 7).

Contratos de entrada/salida de la superficie administrativa. Las respuestas usan
IDs como ``str`` (el dominio los modela como ``PlatformId`` tipado, que no cruza
la frontera HTTP en crudo). Los request bodies son ``StrictModel`` (``extra
forbid``): un ``actor_id`` u otro campo no declarado que un cliente intente
inyectar se rechaza con 422; la identidad **nunca** viene del body (invariante
§Actor). Los mapeos ``*_to_schema`` traducen el modelo de dominio a su schema.

Los request bodies de creación de proyecto y de versión de configuración reusan
los modelos validados de la capa de aplicación para no duplicar la estructura
anidada de tipos documentales, perfiles de embedding y bindings.
"""

from __future__ import annotations

from datetime import datetime

from ingestion.schemas.common import StrictModel
from pydantic import Field

from rag_platform.application.variant_matrix_service import VariantMatrixCell
from rag_platform.application.release_build_service import RagReleaseBuildReport
from rag_platform.domain.models import (
    CorpusOrganizationPolicy,
    CorpusSnapshot,
    DocumentTypeTemplate,
    ProjectConfiguration,
    ProjectDocumentType,
    ProjectEmbeddingProfile,
    RagProject,
    RagVariant,
)
from rag_platform.domain.lifecycle import RagRelease


# --------------------------------------------------------------------------- #
# Proyecto y configuración                                                     #
# --------------------------------------------------------------------------- #


class DocumentTypeSchema(StrictModel):
    code: str
    display_name: str
    template: str


class EmbeddingProfileSchema(StrictModel):
    embedding_profile_id: str
    enabled: bool


class TargetBindingSchema(StrictModel):
    binding_key: str
    indexing_target_id: str
    embedding_profile_id: str


class ProjectConfigurationSchema(StrictModel):
    version: int
    corpus_organization_policy: str
    document_types: list[DocumentTypeSchema]
    embedding_profiles: list[EmbeddingProfileSchema]
    target_bindings: list[TargetBindingSchema]
    created_at: datetime


class ProjectSchema(StrictModel):
    project_id: str
    display_name: str
    state: str
    configuration: ProjectConfigurationSchema
    created_at: datetime


class CreateProjectRequestSchema(StrictModel):
    """Alta de proyecto por HTTP.

    **No** expone ``target_bindings``: un binding acopla ``binding_key`` a un
    ``indexing_target_id`` físico, y el contrato prohíbe que el cliente elija el
    target físico (invariante §Seguridad). Los bindings se provisionan
    server-side (seed/admin) y se leen versionados; el cliente solo declara
    plantilla, política y perfiles de embedding (identidades lógicas globales).
    """

    project_slug: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    document_type_template: DocumentTypeTemplate = DocumentTypeTemplate.GENERIC
    corpus_organization_policy: CorpusOrganizationPolicy = (
        CorpusOrganizationPolicy.SOURCE_FOLDERS_V1
    )
    embedding_profiles: tuple[ProjectEmbeddingProfile, ...] = Field(
        default_factory=tuple
    )


class UpdateProjectConfigurationRequestSchema(StrictModel):
    """Nueva versión de configuración por HTTP.

    Igual que el alta, **no** expone ``target_bindings`` (no filtra el target
    físico al OpenAPI ni al frontend de Fase 8). El versionado de bindings es
    server-side.
    """

    corpus_organization_policy: CorpusOrganizationPolicy
    document_types: tuple[ProjectDocumentType, ...] = Field(default_factory=tuple)
    embedding_profiles: tuple[ProjectEmbeddingProfile, ...] = Field(
        default_factory=tuple
    )


class UpdateProjectRequestSchema(StrictModel):
    """Metadatos mutables de un proyecto (solo ``display_name``; identidad inmutable)."""

    display_name: str = Field(min_length=1, max_length=256)


# --------------------------------------------------------------------------- #
# Variantes                                                                    #
# --------------------------------------------------------------------------- #


class VariantMatrixCellSchema(StrictModel):
    cell_id: str
    processing_profile_id: str
    chunking_profile_id: str
    embedding_profile_id: str
    target_binding_key: str
    configuration_version: int
    buildable: bool
    blocked_reason: str | None = None


class VariantSchema(StrictModel):
    rag_variant_id: str
    project_id: str
    processing_profile_id: str
    chunking_profile_id: str
    embedding_profile_id: str
    semantic_recipe_fingerprint: str
    state: str
    created_at: datetime


class CreateVariantRequestSchema(StrictModel):
    """Solo selección de celda de matriz reconfirmada (nunca IDs físicos libres)."""

    cell_id: str = Field(min_length=1)
    variant_slug: str = Field(min_length=1, max_length=128)


# --------------------------------------------------------------------------- #
# Corpus snapshots                                                             #
# --------------------------------------------------------------------------- #


class CorpusSnapshotDocumentSchema(StrictModel):
    ordinal: int
    source_document_revision_id: str
    eligibility_decision: str


class CorpusSnapshotSchema(StrictModel):
    corpus_snapshot_id: str
    project_id: str
    documents: list[CorpusSnapshotDocumentSchema]
    document_count: int
    manifest_hash: str
    created_at: datetime


class CreateCorpusSnapshotRequestSchema(StrictModel):
    """Congela un snapshot inmutable; el server valida elegibilidad fail-closed.

    ``project_id`` es el ID **canónico completo** (``proj_...``), igual que en el
    resto de rutas; el server lo valida y deriva el slug. Nunca el slug crudo.
    """

    project_id: str = Field(min_length=1, max_length=160)
    document_revision_ids: list[str] = Field(min_length=1)
    #: Decisión explícita por ``revision_id`` para las revisiones que la requieran.
    eligibility_decisions: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Releases                                                                     #
# --------------------------------------------------------------------------- #


class ReleaseSchema(StrictModel):
    rag_release_id: str
    project_id: str
    rag_variant_id: str
    corpus_snapshot_id: str
    target_binding_key: str
    configuration_version: int
    release_number: int
    state: str
    release_manifest_hash: str | None = None
    created_by: str
    created_at: datetime
    validated_at: datetime | None = None
    reason: str | None = None


class ReleaseBuildReportSchema(StrictModel):
    rag_release_id: str
    revisions_built: int
    reused_stages: int
    built_stages: int


class CreateReleaseDraftRequestSchema(StrictModel):
    """DRAFT: solo la clave lógica ``target_binding_key`` (nunca IDs físicos)."""

    rag_variant_id: str = Field(min_length=1)
    corpus_snapshot_id: str = Field(min_length=1)
    target_binding_key: str = Field(min_length=1, max_length=128)


class RetireReleaseRequestSchema(StrictModel):
    reason: str = Field(min_length=1, max_length=512)


# --------------------------------------------------------------------------- #
# Paginación                                                                   #
# --------------------------------------------------------------------------- #


class PaginatedProjectsSchema(StrictModel):
    items: list[ProjectSchema]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class PaginatedVariantsSchema(StrictModel):
    items: list[VariantSchema]
    page: int
    page_size: int
    total_items: int
    total_pages: int


# --------------------------------------------------------------------------- #
# Mapeos dominio -> schema                                                     #
# --------------------------------------------------------------------------- #


def configuration_to_schema(
    configuration: ProjectConfiguration,
) -> ProjectConfigurationSchema:
    return ProjectConfigurationSchema(
        version=configuration.version,
        corpus_organization_policy=configuration.corpus_organization_policy.value,
        document_types=[
            DocumentTypeSchema(
                code=doc.code,
                display_name=doc.display_name,
                template=doc.template.value,
            )
            for doc in configuration.document_types
        ],
        embedding_profiles=[
            EmbeddingProfileSchema(
                embedding_profile_id=profile.embedding_profile_id,
                enabled=profile.enabled,
            )
            for profile in configuration.embedding_profiles
        ],
        target_bindings=[
            TargetBindingSchema(
                binding_key=binding.binding_key,
                indexing_target_id=binding.indexing_target_id,
                embedding_profile_id=binding.embedding_profile_id,
            )
            for binding in configuration.target_bindings
        ],
        created_at=configuration.created_at,
    )


def project_to_schema(project: RagProject) -> ProjectSchema:
    return ProjectSchema(
        project_id=project.project_id.value,
        display_name=project.display_name,
        state=project.state.value,
        configuration=configuration_to_schema(project.configuration),
        created_at=project.created_at,
    )


def matrix_cell_to_schema(cell: VariantMatrixCell) -> VariantMatrixCellSchema:
    return VariantMatrixCellSchema(
        cell_id=cell.cell_id,
        processing_profile_id=cell.processing_profile_id,
        chunking_profile_id=cell.chunking_profile_id,
        embedding_profile_id=cell.embedding_profile_id,
        target_binding_key=cell.target_binding_key,
        configuration_version=cell.configuration_version,
        buildable=cell.buildable,
        blocked_reason=cell.blocked_reason,
    )


def variant_to_schema(variant: RagVariant) -> VariantSchema:
    return VariantSchema(
        rag_variant_id=variant.rag_variant_id.value,
        project_id=variant.project_id.value,
        processing_profile_id=variant.processing_profile_id.value,
        chunking_profile_id=variant.chunking_profile_id.value,
        embedding_profile_id=variant.embedding_profile_id,
        semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
        state=variant.state.value,
        created_at=variant.created_at,
    )


def snapshot_to_schema(snapshot: CorpusSnapshot) -> CorpusSnapshotSchema:
    return CorpusSnapshotSchema(
        corpus_snapshot_id=snapshot.corpus_snapshot_id.value,
        project_id=snapshot.project_id.value,
        documents=[
            CorpusSnapshotDocumentSchema(
                ordinal=doc.ordinal,
                source_document_revision_id=doc.source_document_revision_id.value,
                eligibility_decision=doc.eligibility_decision.value,
            )
            for doc in snapshot.documents
        ],
        document_count=snapshot.document_count,
        manifest_hash=snapshot.manifest_hash,
        created_at=snapshot.created_at,
    )


def release_to_schema(release: RagRelease) -> ReleaseSchema:
    return ReleaseSchema(
        rag_release_id=release.rag_release_id.value,
        project_id=release.project_id.value,
        rag_variant_id=release.rag_variant_id.value,
        corpus_snapshot_id=release.corpus_snapshot_id.value,
        target_binding_key=release.target_binding_key,
        configuration_version=release.configuration_version,
        release_number=release.release_number,
        state=release.state.value,
        release_manifest_hash=release.release_manifest_hash,
        created_by=release.created_by,
        created_at=release.created_at,
        validated_at=release.validated_at,
        reason=release.reason,
    )


def build_report_to_schema(report: RagReleaseBuildReport) -> ReleaseBuildReportSchema:
    return ReleaseBuildReportSchema(
        rag_release_id=report.rag_release_id,
        revisions_built=report.revisions_built,
        reused_stages=report.reused_stages,
        built_stages=report.built_stages,
    )
