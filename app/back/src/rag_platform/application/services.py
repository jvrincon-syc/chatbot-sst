"""Contenedor tipado único de la superficie de aplicación de plataforma (Fase 7).

``RagPlatformServices`` agrupa los casos de uso que el router HTTP de Fase 7
necesita, ya cableados, para que la capa API no construya dependencias ni
conozca repositorios concretos. Task 3 puebla la superficie de
proyectos/configuración; Task 4 **extiende este mismo contenedor** con
variantes, snapshots y releases. No se crea una segunda superficie de servicios.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag_platform.application.corpus_snapshot_service import (
    CreateCorpusSnapshotUseCase,
)
from rag_platform.application.corpus_snapshot_query_service import (
    ListProjectCorpusSnapshotsUseCase,
)
from rag_platform.application.document_query_service import (
    ListProjectDocumentsUseCase,
)
from rag_platform.application.project_normalization_service import (
    NormalizeProjectDocumentsUseCase,
)
from rag_platform.application.project_raw_upload_service import (
    UploadProjectRawDocumentUseCase,
)
from rag_platform.application.project_configuration_service import (
    CreateProjectConfigurationVersionUseCase,
    GetProjectConfigurationUseCase,
    GetProjectConfigurationVersionUseCase,
)
from rag_platform.application.project_query_service import (
    GetProjectUseCase,
    ListChunkingProfilesUseCase,
    ListProcessingProfilesUseCase,
    ListProjectsUseCase,
    UpdateProjectMetadataUseCase,
)
from rag_platform.application.project_service import CreateProjectUseCase
from rag_platform.application.publication_service import PublishRagReleaseUseCase
from rag_platform.application.rebuild_orchestrator import RebuildPlatformArtifactsUseCase
from rag_platform.application.release_build_service import BuildRagReleaseUseCase
from rag_platform.application.release_query_service import (
    GetReleaseUseCase,
    ListProjectReleasesUseCase,
)
from rag_platform.application.release_retirement_service import (
    RetireRagReleaseUseCase,
)
from rag_platform.application.release_service import CreateRagReleaseDraftUseCase
from rag_platform.application.release_validator import ValidateRagReleaseUseCase
from rag_platform.application.variant_matrix_service import (
    CreateRagVariantFromMatrixCellUseCase,
    GetVariantMatrixUseCase,
)
from rag_platform.application.variant_query_service import (
    ListProjectVariantsUseCase,
)


@dataclass(frozen=True)
class RagPlatformServices:
    """Superficie de aplicación de plataforma cableada para la capa API.

    Contenedor **único** para Fase 7 (no se crea una segunda superficie): Task 3
    puebla proyectos/configuración y Task 4 extiende con variantes, snapshots y
    releases.
    """

    # Proyectos / configuración — Task 3
    create_project: CreateProjectUseCase
    get_project: GetProjectUseCase
    list_projects: ListProjectsUseCase
    update_project_metadata: UpdateProjectMetadataUseCase
    get_project_configuration: GetProjectConfigurationUseCase
    get_project_configuration_version: GetProjectConfigurationVersionUseCase
    create_project_configuration_version: CreateProjectConfigurationVersionUseCase
    list_processing_profiles: ListProcessingProfilesUseCase
    list_chunking_profiles: ListChunkingProfilesUseCase

    # Variantes — Task 4
    get_variant_matrix: GetVariantMatrixUseCase
    create_variant_from_matrix_cell: CreateRagVariantFromMatrixCellUseCase
    list_project_variants: ListProjectVariantsUseCase

    # Documentos (intake project-aware) — Gate 1 Fase 8
    list_project_documents: ListProjectDocumentsUseCase
    upload_project_document: UploadProjectRawDocumentUseCase
    normalize_project_documents: NormalizeProjectDocumentsUseCase

    # Corpus snapshot — Task 4
    create_corpus_snapshot: CreateCorpusSnapshotUseCase
    list_project_corpus_snapshots: ListProjectCorpusSnapshotsUseCase

    # Releases — Task 4
    create_release_draft: CreateRagReleaseDraftUseCase
    get_release: GetReleaseUseCase
    list_project_releases: ListProjectReleasesUseCase
    build_release: BuildRagReleaseUseCase
    validate_release: ValidateRagReleaseUseCase
    publish_release: PublishRagReleaseUseCase
    retire_release: RetireRagReleaseUseCase
    rebuild_platform: RebuildPlatformArtifactsUseCase | None
