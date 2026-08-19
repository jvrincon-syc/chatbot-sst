"""Casos de uso de lectura de variantes de un proyecto (superficie Fase 7).

Listar variantes es una lectura pura sobre el catálogo ``rag_variants``: el
router HTTP la invoca sin SQL ni reglas de negocio. La escritura de variantes va
por el wrapper de celda de matriz (``variant_matrix_service``), nunca por IDs
libres.
"""

from __future__ import annotations

from rag_platform.application.context import (
    PlatformAccessPolicy,
    RagVariantRepository,
)
from rag_platform.application.platform_access import (
    PlatformActor,
    require_project_operator,
)
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import RagVariant


class ListProjectVariantsUseCase:
    """Lista las variantes RAG de un proyecto (orden estable, fail-closed por scope)."""

    def __init__(
        self,
        *,
        variants: RagVariantRepository,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._variants = variants
        self._access_policy = access_policy

    def execute(
        self, project_id: PlatformId, *, actor: PlatformActor
    ) -> tuple[RagVariant, ...]:
        """Devuelve las variantes del proyecto; un actor fuera de scope falla cerrado."""

        require_project_operator(
            policy=self._access_policy, actor=actor, project_id=project_id
        )
        return tuple(self._variants.list_for_project(project_id))
