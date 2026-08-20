"""Normalización project-aware de documentos ya registrados (Gate 1, Fase 8).

Orquesta (no reimplementa el motor): autoriza por scope, resuelve la variante RAG
—que aporta el perfil de procesamiento y la provenance de receta—, valida que
cada revisión pertenezca al proyecto (fail-closed cross-project) y delega la
normalización física en el puerto ``ProjectDocumentNormalizer``. El motor real
(``run_pipeline``) vive tras ese puerto para que el caso de uso sea unit-testeable
sin pdfium/tesseract y la capa de aplicación no importe el engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from rag_platform.application.context import (
    PlatformAccessPolicy,
    ProcessingProfileRepository,
    ProjectRepository,
    RagVariantRepository,
    SourceDocumentRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.errors import (
    RevisionProjectMismatch,
    VariantProjectMismatch,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import RagProject, SourceDocumentRevision


@dataclass(frozen=True)
class ProjectNormalizeOutcome:
    """Resultado auditable de una corrida de normalización por proyecto."""

    rag_variant_id: str
    processed: int
    needs_review: int
    skipped: int
    failed: int
    revision_ids: tuple[str, ...]


@runtime_checkable
class ProjectDocumentNormalizer(Protocol):
    """Puerto que normaliza físicamente un conjunto de revisiones ya identificadas.

    La implementación (infra) escanea los bytes raw, corre el preflight de
    identidad fail-closed y reutiliza el motor de ingesta; nunca la capa de
    aplicación.
    """

    def normalize(
        self,
        *,
        project: RagProject,
        revisions: tuple[SourceDocumentRevision, ...],
        processing_profile_id: str,
        processing_profile_fingerprint: str,
        rag_variant_id: str | None,
        semantic_recipe_fingerprint: str | None,
        force: bool,
    ) -> ProjectNormalizeOutcome:
        """Normaliza las revisiones dadas y devuelve el resumen."""


class NormalizeProjectDocumentsUseCase:
    """Normaliza revisiones de un proyecto bajo la receta de una variante RAG."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        documents: SourceDocumentRepository,
        variants: RagVariantRepository,
        processing_profiles: ProcessingProfileRepository,
        normalizer: ProjectDocumentNormalizer,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._projects = projects
        self._documents = documents
        self._variants = variants
        self._processing_profiles = processing_profiles
        self._normalizer = normalizer
        self._access_policy = access_policy

    def execute(
        self,
        *,
        project_id: PlatformId,
        rag_variant_id: PlatformId,
        document_revision_ids: Sequence[str],
        force: bool,
        actor: PlatformActor,
    ) -> ProjectNormalizeOutcome:
        """Normaliza las revisiones pedidas o falla cerrado.

        Raises:
            PlatformAccessDenied: Actor fuera de scope.
            ProjectNotFound / RagVariantNotFound: Proyecto o variante inexistentes.
            VariantProjectMismatch: La variante es de otro proyecto.
            RevisionProjectMismatch: Alguna revisión es de otro proyecto.
            SourceDocumentRevisionNotFound: Alguna revisión no está registrada.
            ProjectNormalizationIncomplete: Falta identidad o bytes raw (preflight).
        """

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        project = self._projects.get(project_id)
        variant = self._variants.get(rag_variant_id)
        if variant.project_id != project_id:
            raise VariantProjectMismatch(
                f"variant {rag_variant_id.value} is not owned by {project_id.value}"
            )
        profile = self._processing_profiles.get(variant.processing_profile_id)

        revisions: list[SourceDocumentRevision] = []
        seen: set[str] = set()
        for raw_id in document_revision_ids:
            revision_id = PlatformId.parse(
                IdentityKind.SOURCE_DOCUMENT_REVISION, raw_id
            )
            if revision_id.value in seen:
                continue
            seen.add(revision_id.value)
            revision = self._documents.get_revision(revision_id)
            if revision.project_id != project_id:
                raise RevisionProjectMismatch(
                    f"revision {revision_id.value} is not owned by {project_id.value}"
                )
            revisions.append(revision)

        return self._normalizer.normalize(
            project=project,
            revisions=tuple(revisions),
            processing_profile_id=variant.processing_profile_id.value,
            processing_profile_fingerprint=profile.fingerprint,
            rag_variant_id=variant.rag_variant_id.value,
            semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
            force=force,
        )
