"""Orquestador de persistencia del catálogo ``normalized`` por proyecto (Task 5).

``PersistNormalizedArtifactCatalogUseCase`` **compone** piezas existentes; no
reimplementa el motor de normalización:

1. resuelve el normalizado por identidad exacta con
   ``ResolveNormalizedArtifactUseCase`` (reusa o construye una vez);
2. lee la receta de procesamiento (proveedor/motor/origen/config sanitizada) del
   ``ProcessingProfileRepository``;
3. si el normalizado nació en contexto de variante, lee la variante para adjuntar
   su ``semantic_recipe_fingerprint`` como provenance;
4. hace ``upsert`` del sidecar físico en ``project_normalized_document_artifacts``.

La identidad física del artefacto es ``project + revisión + fingerprint de
procesamiento`` (``normalized_document_id`` determinista). ``rag_variant_id`` y
``semantic_recipe_fingerprint`` son provenance auditable nullable, nunca dueños
de la identidad. La dirección de dependencias se respeta: este servicio solo
conoce puertos de aplicación y el dominio, nunca PostgreSQL, FastAPI ni SDKs.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from ingestion.paths import ArtifactPaths
from ingestion.schemas.artifacts import PlatformArtifactProvenance
from ingestion.schemas.common import RelativePosixPath, StrictModel
from pydantic import Field

from rag_platform.application.context import (
    NormalizedArtifactCatalogRepository,
    ProcessingProfileRepository,
)
from rag_platform.application.document_revision_service import (
    ResolveNormalizedArtifactUseCase,
)
from rag_platform.domain.artifact_catalog import NormalizedDocumentArtifactRecord
from rag_platform.domain.identity import (
    IdentityKind,
    PlatformId,
    ProjectDocumentContext,
    normalized_document_id,
)
from rag_platform.domain.models import RagVariant


_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class RagVariantReader(Protocol):
    """Puerto estrecho para leer una variante por su identidad.

    El adaptador Postgres ``PostgresRagVariantRepository`` ya satisface este
    contrato con su método ``get``; el servicio solo necesita la lectura, no la
    escritura, así que segrega la interfaz (SOLID/ISP).
    """

    def get(self, rag_variant_id: PlatformId) -> RagVariant:
        """Devuelve la variante o lanza ``RagVariantNotFound``."""


class PersistNormalizedArtifactCatalogRequest(StrictModel):
    """Entrada validada para persistir el catálogo físico de un normalizado.

    ``rag_variant_id`` es opcional: solo viaja cuando el normalizado nació en el
    contexto de una variante. Los identificadores se validan de forma estricta al
    construir el ``PlatformId`` y el registro físico (fail-closed).
    """

    project_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    source_document_revision_id: str = Field(min_length=1)
    processing_profile_id: str = Field(min_length=1)
    source_relpath: RelativePosixPath
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    processing_status: str = Field(pattern=r"^(processed|needs_review)$")
    rag_variant_id: Optional[str] = None


class PersistNormalizedArtifactCatalogUseCase:
    """Compone resolución de normalizado, receta y provenance de variante."""

    def __init__(
        self,
        *,
        resolve: ResolveNormalizedArtifactUseCase,
        processing_profiles: ProcessingProfileRepository,
        variants: RagVariantReader,
        catalog: NormalizedArtifactCatalogRepository,
    ) -> None:
        self._resolve = resolve
        self._processing_profiles = processing_profiles
        self._variants = variants
        self._catalog = catalog

    def execute(
        self, request: PersistNormalizedArtifactCatalogRequest
    ) -> NormalizedDocumentArtifactRecord:
        """Resuelve el normalizado y persiste su sidecar físico enriquecido.

        Args:
            request: Datos validados del normalizado y su contexto de proyecto.

        Returns:
            El ``NormalizedDocumentArtifactRecord`` persistido.

        Raises:
            ProcessingProfileNotFound: Si la receta de procesamiento no existe.
            RagVariantNotFound: Si se pidió provenance de una variante inexistente.
        """

        project_pid = PlatformId(kind=IdentityKind.PROJECT, value=request.project_id)
        source_document_pid = PlatformId(
            kind=IdentityKind.SOURCE_DOCUMENT, value=request.source_document_id
        )
        revision_pid = PlatformId(
            kind=IdentityKind.SOURCE_DOCUMENT_REVISION,
            value=request.source_document_revision_id,
        )
        profile_pid = PlatformId(
            kind=IdentityKind.PROCESSING_PROFILE, value=request.processing_profile_id
        )

        # La receta es la autoridad del fingerprint de procesamiento y del
        # proveedor/motor/origen; nunca lleva credenciales (solo config sanitizada).
        profile = self._processing_profiles.get(profile_pid)

        context = ProjectDocumentContext(
            project_id=project_pid,
            source_document_id=source_document_pid,
            source_document_revision_id=revision_pid,
            processing_profile_id=profile_pid,
        )
        artifact = self._resolve.resolve_or_build(context)

        provenance = PlatformArtifactProvenance()
        if request.rag_variant_id is not None:
            variant = self._variants.get(
                PlatformId(kind=IdentityKind.RAG_VARIANT, value=request.rag_variant_id)
            )
            provenance = PlatformArtifactProvenance(
                rag_variant_id=variant.rag_variant_id.value,
                semantic_recipe_fingerprint=variant.semantic_recipe_fingerprint,
            )

        paths = ArtifactPaths.for_source(request.source_relpath)
        record = NormalizedDocumentArtifactRecord(
            normalized_document_id=normalized_document_id(
                project_id=project_pid.value,
                source_document_revision_id=revision_pid.value,
                processing_profile_fingerprint=profile.fingerprint,
            ),
            project_id=project_pid.value,
            source_document_revision_id=revision_pid.value,
            logical_document_id=source_document_pid.value,
            processing_profile_id=profile_pid.value,
            processing_profile_fingerprint=profile.fingerprint,
            processing_origin=profile.origin,
            parser_provider=profile.provider,
            parser_engine=profile.engine,
            observed_revision=profile.observed_revision,
            sanitized_config_json=dict(profile.sanitized_config),
            schema_version=artifact.schema_version,
            markdown_relpath=paths.markdown,
            metadata_relpath=paths.metadata,
            pages_relpath=paths.pages,
            tables_relpath=paths.tables,
            forms_relpath=paths.forms,
            source_hash=request.source_hash,
            processing_status=request.processing_status,
            provenance=provenance,
        )
        stored = self._catalog.upsert(record)

        _LOGGER.info(
            "persisted normalized artifact catalog",
            extra={
                "project_id": stored.project_id,
                "document_id": stored.logical_document_id,
                "source_document_revision_id": stored.source_document_revision_id,
                "normalized_document_id": stored.normalized_document_id,
                "capability": "ingestion.normalized_catalog",
                "provider": stored.parser_provider,
                "rag_variant_id": stored.rag_variant_id,
                "status": "registered",
            },
        )
        return stored
