"""Matriz de variantes construibles y creación reconfirmada (superficie Fase 7).

La matriz enumera las celdas ``(perfil de procesamiento × perfil de chunking ×
binding target)`` de la **configuración vigente** de un proyecto. Cada celda
lleva su ``configuration_version`` como parte de la identidad (``cell_id``), de
modo que ``POST /variants`` no acepte IDs libres sino una celda revalidada.

Fail-closed contra TOCTOU: si la configuración del proyecto avanza entre el
``GET`` de la matriz y el ``POST`` de la variante, la celda pinneada a una
versión anterior deja de aparecer en la matriz vigente y se rechaza con
``StaleVariantMatrixCell``. La creación reusa ``CreateRagVariantUseCase`` con la
``configuration_version`` **explícita** de la celda; nunca re-resuelve la versión
actual a espaldas de la reconfirmación.
"""

from __future__ import annotations

from pydantic import Field

from ingestion.schemas.common import StrictModel
from rag_platform.application.context import (
    ChunkingProfileRepository,
    ProcessingProfileRepository,
    ProjectRepository,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.recipe_service import (
    CreateRagVariantRequest,
    CreateRagVariantUseCase,
)
from rag_platform.domain.errors import (
    InvalidVariantMatrixCell,
    StaleVariantMatrixCell,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import RagVariant

#: Separador de campos del ``cell_id``. Los IDs de plataforma solo admiten
#: ``[a-z0-9-]`` en su cuerpo, así que ``|`` nunca aparece dentro de un campo.
_CELL_SEP = "|"
_CELL_FIELDS = 5


class VariantMatrixCell(StrictModel):
    """Una celda construible de la matriz de variantes de un proyecto.

    ``cell_id`` codifica los IDs persistidos, no estrategias:
    ``processing_profile_id | chunking_profile_id | embedding_profile_id |
    target_binding_key | configuration_version``.
    """

    cell_id: str = Field(min_length=1)
    processing_profile_id: str = Field(min_length=1)
    chunking_profile_id: str = Field(min_length=1)
    embedding_profile_id: str = Field(min_length=1)
    target_binding_key: str = Field(min_length=1)
    configuration_version: int = Field(ge=1)
    buildable: bool
    blocked_reason: str | None = None


def platform_id_body(identity: PlatformId) -> str:
    """Devuelve el cuerpo (sin prefijo) de un ``PlatformId``.

    Evita duplicar prefijos (``proj_proj_...``) al construir un
    ``CreateRagVariantRequest``, cuyos campos esperan el cuerpo del ID y no el ID
    completo (el caso de uso reañade el prefijo tipado).
    """

    prefix = f"{identity.kind.value}_"
    return identity.value.removeprefix(prefix)


def _build_cell_id(
    *,
    processing_profile_id: str,
    chunking_profile_id: str,
    embedding_profile_id: str,
    target_binding_key: str,
    configuration_version: int,
) -> str:
    return _CELL_SEP.join(
        (
            processing_profile_id,
            chunking_profile_id,
            embedding_profile_id,
            target_binding_key,
            str(configuration_version),
        )
    )


def _parse_cell_id(cell_id: str) -> tuple[str, str, str, str, int]:
    """Valida el formato de un ``cell_id`` o falla cerrado (``InvalidVariantMatrixCell``)."""

    parts = cell_id.split(_CELL_SEP)
    if len(parts) != _CELL_FIELDS:
        raise InvalidVariantMatrixCell(cell_id)
    processing, chunking, embedding, binding_key, raw_version = parts
    if not all((processing, chunking, embedding, binding_key, raw_version)):
        raise InvalidVariantMatrixCell(cell_id)
    try:
        version = int(raw_version)
    except ValueError as error:
        raise InvalidVariantMatrixCell(cell_id) from error
    if version < 1:
        raise InvalidVariantMatrixCell(cell_id)
    return processing, chunking, embedding, binding_key, version


class GetVariantMatrixUseCase:
    """Construye la matriz de variantes construibles de la configuración vigente."""

    def __init__(
        self,
        *,
        projects: ProjectRepository,
        processing_profiles: ProcessingProfileRepository,
        chunking_profiles: ChunkingProfileRepository,
    ) -> None:
        self._projects = projects
        self._processing_profiles = processing_profiles
        self._chunking_profiles = chunking_profiles

    def execute(self, *, project_id: PlatformId) -> tuple[VariantMatrixCell, ...]:
        """Devuelve las celdas ``(procesamiento × chunking × binding)`` vigentes."""

        configuration = self._projects.get(project_id).configuration
        version = configuration.version
        enabled_embeddings = {
            profile.embedding_profile_id
            for profile in configuration.embedding_profiles
            if profile.enabled
        }
        processing = self._processing_profiles.list_for_project(project_id)
        chunking = self._chunking_profiles.list_for_project(project_id)

        cells: list[VariantMatrixCell] = []
        for binding in configuration.target_bindings:
            embedding_id = binding.embedding_profile_id
            buildable = embedding_id in enabled_embeddings
            blocked_reason = None if buildable else "embedding_profile_not_enabled"
            for proc in processing:
                for chunk in chunking:
                    cell_id = _build_cell_id(
                        processing_profile_id=proc.processing_profile_id.value,
                        chunking_profile_id=chunk.chunking_profile_id.value,
                        embedding_profile_id=embedding_id,
                        target_binding_key=binding.binding_key,
                        configuration_version=version,
                    )
                    cells.append(
                        VariantMatrixCell(
                            cell_id=cell_id,
                            processing_profile_id=proc.processing_profile_id.value,
                            chunking_profile_id=chunk.chunking_profile_id.value,
                            embedding_profile_id=embedding_id,
                            target_binding_key=binding.binding_key,
                            configuration_version=version,
                            buildable=buildable,
                            blocked_reason=blocked_reason,
                        )
                    )
        return tuple(cells)

    def get_cell(
        self, *, project_id: PlatformId, cell_id: str
    ) -> VariantMatrixCell:
        """Reconfirma que ``cell_id`` sigue en la matriz vigente (fail-closed).

        Raises:
            InvalidVariantMatrixCell: Si el ``cell_id`` está malformado.
            StaleVariantMatrixCell: Si la celda ya no aparece en la configuración
                vigente (versión avanzada, binding retirado, perfil eliminado).
        """

        _parse_cell_id(cell_id)  # valida el formato antes de reconstruir la matriz.
        for cell in self.execute(project_id=project_id):
            if cell.cell_id == cell_id:
                return cell
        raise StaleVariantMatrixCell(cell_id)


class CreateRagVariantFromMatrixCellUseCase:
    """Crea una variante a partir de una celda de matriz reconfirmada.

    ``POST /variants`` solo acepta ``cell_id + variant_slug``; nunca IDs libres de
    procesamiento/chunking/embedding. La celda se revalida contra la
    configuración vigente (incluida su versión) antes de crear.
    """

    def __init__(
        self,
        *,
        matrix: GetVariantMatrixUseCase,
        create_variant: CreateRagVariantUseCase,
    ) -> None:
        self._matrix = matrix
        self._create_variant = create_variant

    def execute(
        self,
        *,
        project_id: PlatformId,
        cell_id: str,
        variant_slug: str,
        actor: PlatformActor,
    ) -> RagVariant:
        """Reconfirma la celda y crea la variante con su versión explícita.

        Raises:
            InvalidVariantMatrixCell / StaleVariantMatrixCell: Celda inválida o
                desactualizada (fail-closed).
            PlatformAccessDenied: Si el actor no puede operar el proyecto.
        """

        cell = self._matrix.get_cell(project_id=project_id, cell_id=cell_id)

        processing_pid = PlatformId.parse(
            IdentityKind.PROCESSING_PROFILE, cell.processing_profile_id
        )
        chunking_pid = PlatformId.parse(
            IdentityKind.CHUNKING_PROFILE, cell.chunking_profile_id
        )
        request = CreateRagVariantRequest(
            project_id=platform_id_body(project_id),
            variant_slug=variant_slug,
            processing_profile_id=platform_id_body(processing_pid),
            chunking_profile_id=platform_id_body(chunking_pid),
            embedding_profile_id=cell.embedding_profile_id,
            target_binding_key=cell.target_binding_key,
            configuration_version=cell.configuration_version,
        )
        return self._create_variant.execute(request, actor_id=actor.actor_id)
