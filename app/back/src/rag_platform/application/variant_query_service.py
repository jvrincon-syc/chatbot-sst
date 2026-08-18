"""Casos de uso de lectura de variantes de un proyecto (superficie Fase 7).

Listar variantes es una lectura pura sobre el catálogo ``rag_variants``: el
router HTTP la invoca sin SQL ni reglas de negocio. La escritura de variantes va
por el wrapper de celda de matriz (``variant_matrix_service``), nunca por IDs
libres.
"""

from __future__ import annotations

from rag_platform.application.context import RagVariantRepository
from rag_platform.domain.identity import PlatformId
from rag_platform.domain.models import RagVariant


class ListProjectVariantsUseCase:
    """Lista las variantes RAG declaradas por un proyecto (orden estable)."""

    def __init__(self, *, variants: RagVariantRepository) -> None:
        self._variants = variants

    def execute(self, project_id: PlatformId) -> tuple[RagVariant, ...]:
        """Devuelve las variantes del proyecto, ordenadas de forma determinista."""

        return tuple(self._variants.list_for_project(project_id))
