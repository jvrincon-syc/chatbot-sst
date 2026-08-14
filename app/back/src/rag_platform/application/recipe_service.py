"""Caso de uso de creación de variante RAG (Fase 1).

Computa el ``semantic_recipe_fingerprint`` de la receta y aplica la unicidad
``UNIQUE(project_id, semantic_recipe_fingerprint)`` mientras la variante está
activa (plan §4.4). Falla cerrado si el binding target es incompatible con el
perfil de embedding o si la receta usa una revisión no verificable sin
attestation explícita (plan §Fase 1, política fail-closed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from ingestion.schemas.common import StrictModel
from pydantic import Field


@runtime_checkable
class EmbeddingProfileReader(Protocol):
    """Puerto estrecho para leer un perfil de embedding global (ADR-005).

    Solo se necesita ``get``; el objeto devuelto debe exponer
    ``expected_fingerprint()`` (el digest de su config semántica). El adaptador
    ``PostgresEmbeddingProfileRepository`` ya satisface este contrato.
    """

    def get(self, profile_id: str) -> Any:
        """Devuelve el perfil de embedding o lanza si no existe."""

from rag_platform.application.context import (
    ChunkingProfileRepository,
    PlatformAccessPolicy,
    ProcessingProfileRepository,
    RagVariantRepository,
    TargetBindingResolver,
)
from rag_platform.domain.errors import (
    DuplicateVariantRecipe,
    IncompatibleTargetBinding,
    ProfileProjectMismatch,
    UnverifiableRecipeRevision,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import (
    ProfileVerificationStatus,
    RagVariant,
    compute_semantic_recipe_fingerprint,
)


class CreateRagVariantRequest(StrictModel):
    """Entrada validada para crear una variante RAG.

    Los IDs de perfil son ``str`` de cuerpo (sin prefijo): el caso de uso los
    resuelve a ``PlatformId`` tipados. ``target_binding_key`` es una clave lógica
    de la allowlist del proyecto, nunca un ``indexing_target_id`` directo.
    """

    variant_slug: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1)
    processing_profile_id: str = Field(min_length=1)
    chunking_profile_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    target_binding_key: str = Field(min_length=1)
    allow_unverifiable_revision: bool = False


class CreateRagVariantUseCase:
    """Crea una variante RAG con receta semántica inmutable."""

    def __init__(
        self,
        *,
        variants: RagVariantRepository,
        processing_profiles: ProcessingProfileRepository,
        chunking_profiles: ChunkingProfileRepository,
        embedding_profiles: EmbeddingProfileReader,
        target_bindings: TargetBindingResolver,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._variants = variants
        self._processing_profiles = processing_profiles
        self._chunking_profiles = chunking_profiles
        self._embedding_profiles = embedding_profiles
        self._target_bindings = target_bindings
        self._access_policy = access_policy

    def execute(
        self, request: CreateRagVariantRequest, *, actor_id: str
    ) -> RagVariant:
        """Crea y persiste una variante RAG.

        Args:
            request: Datos validados de la receta.
            actor_id: Operador autenticado; autorizado por ``PlatformAccessPolicy``.

        Returns:
            La ``RagVariant`` persistida.

        Raises:
            PlatformAccessDenied: Si el actor no es operador autorizado.
            ProcessingProfileNotFound / ChunkingProfileNotFound: Perfil ausente.
            ProfileProjectMismatch: Un perfil pertenece a otro proyecto.
            IncompatibleTargetBinding: Binding incompatible con el embedding.
            UnverifiableRecipeRevision: Revisión no verificable sin attestation.
            DuplicateVariantRecipe: Ya existe variante activa con esa receta.
        """

        self._access_policy.require_operator(actor_id=actor_id)

        project_id = PlatformId(
            kind=IdentityKind.PROJECT, value=f"{IdentityKind.PROJECT.value}_{request.project_id}"
        )
        processing_id = PlatformId(
            kind=IdentityKind.PROCESSING_PROFILE,
            value=f"{IdentityKind.PROCESSING_PROFILE.value}_{request.processing_profile_id}",
        )
        chunking_id = PlatformId(
            kind=IdentityKind.CHUNKING_PROFILE,
            value=f"{IdentityKind.CHUNKING_PROFILE.value}_{request.chunking_profile_id}",
        )

        processing = self._processing_profiles.get(processing_id)
        chunking = self._chunking_profiles.get(chunking_id)

        # Los perfiles deben pertenecer al mismo proyecto que la variante.
        if processing.project_id != project_id:
            raise ProfileProjectMismatch(processing.processing_profile_id.value)
        if chunking.project_id != project_id:
            raise ProfileProjectMismatch(chunking.chunking_profile_id.value)

        # Fail-closed: una revisión no verificable exige attestation explícita.
        if (
            processing.status is ProfileVerificationStatus.UNVERIFIABLE
            and not request.allow_unverifiable_revision
        ):
            raise UnverifiableRecipeRevision(processing.processing_profile_id.value)

        # Fail-closed: el target debe estar en la allowlist y ser compatible con
        # el perfil de embedding de la variante.
        binding = self._target_bindings.find_binding(
            project_id, request.target_binding_key
        )
        if binding is None or binding.embedding_profile_id != request.embedding_profile_id:
            raise IncompatibleTargetBinding(request.target_binding_key)

        # La config del motor de embedding (dimensión/modelo/normalización/métrica) queda
        # fijada en la receta vía su fingerprint, no solo por el id del perfil.
        embedding_profile = self._embedding_profiles.get(request.embedding_profile_id)
        embedding_configuration_fingerprint = (
            embedding_profile.expected_fingerprint().value
        )

        fingerprint = compute_semantic_recipe_fingerprint(
            processing_provider=processing.provider,
            processing_engine=processing.engine,
            processing_revision=processing.observed_revision,
            processing_config=processing.sanitized_config,
            chunking_strategy=chunking.strategy,
            chunking_config=chunking.sanitized_config,
            embedding_profile_id=request.embedding_profile_id,
            embedding_configuration_fingerprint=embedding_configuration_fingerprint,
        )

        if (
            self._variants.find_active_by_fingerprint(project_id, fingerprint)
            is not None
        ):
            raise DuplicateVariantRecipe(fingerprint)

        variant = RagVariant(
            rag_variant_id=PlatformId(
                kind=IdentityKind.RAG_VARIANT,
                value=f"{IdentityKind.RAG_VARIANT.value}_{request.variant_slug}",
            ),
            project_id=project_id,
            processing_profile_id=processing_id,
            chunking_profile_id=chunking_id,
            embedding_profile_id=request.embedding_profile_id,
            semantic_recipe_fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc),
        )
        return self._variants.add(variant)
