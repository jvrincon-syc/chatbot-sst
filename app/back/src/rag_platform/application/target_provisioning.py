"""Provisioning server-side de target bindings desde el catálogo global (Fase 7).

El cliente HTTP declara solo perfiles de embedding **lógicos**; nunca elige el
``indexing_target_id`` físico ni la tabla vectorial (invariante §Seguridad). Este
servicio deriva, para cada perfil de embedding habilitado, un
``ProjectIndexingTargetBinding`` resolviendo un ``IndexingTarget`` compatible del
catálogo global de targets (el mismo que usan embedding/indexing; no se crea un
segundo catálogo).

Fail-closed: si no existe un target compatible para un perfil, **no se fabrica**
binding; el proyecto queda sin celda construible para ese perfil hasta que exista
un target compatible. El binding_key derivado es lógico (el propio
``embedding_profile_id``), de modo que ni el binding_key ni el target físico
provienen del cliente.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rag_platform.domain.models import (
    ProjectEmbeddingProfile,
    ProjectIndexingTargetBinding,
)


@runtime_checkable
class IndexingTargetView(Protocol):
    """Vista mínima de un indexing target del catálogo global (estructural)."""

    indexing_target_id: str
    embedding_profile_id: str | None


@runtime_checkable
class IndexingTargetCatalog(Protocol):
    """Catálogo global de indexing targets.

    Lo satisface el repositorio de targets de embedding
    (``InMemoryIndexingTargetRepository`` / ``PostgresIndexingTargetRepository``),
    que ya expone ``list_targets()``. No se introduce un segundo catálogo.
    """

    def list_targets(self) -> Sequence[IndexingTargetView]:
        """Devuelve todos los indexing targets registrados."""


class TargetBindingProvisioner:
    """Deriva bindings server-side para los perfiles de embedding declarados."""

    def __init__(self, *, targets: IndexingTargetCatalog) -> None:
        self._targets = targets

    def provision(
        self, embedding_profiles: Sequence[ProjectEmbeddingProfile]
    ) -> tuple[ProjectIndexingTargetBinding, ...]:
        """Deriva un binding por perfil de embedding habilitado con target compatible.

        Un perfil deshabilitado o sin target compatible no produce binding
        (fail-closed, sin fabricar identidad física).
        """

        catalog = list(self._targets.list_targets())
        bindings: list[ProjectIndexingTargetBinding] = []
        seen: set[str] = set()
        for profile in embedding_profiles:
            if not profile.enabled or profile.embedding_profile_id in seen:
                continue
            target_id = _compatible_target(catalog, profile.embedding_profile_id)
            if target_id is None:
                continue
            seen.add(profile.embedding_profile_id)
            bindings.append(
                ProjectIndexingTargetBinding(
                    binding_key=profile.embedding_profile_id,
                    indexing_target_id=target_id,
                    embedding_profile_id=profile.embedding_profile_id,
                )
            )
        return tuple(bindings)


def _compatible_target(
    catalog: Sequence[IndexingTargetView], embedding_profile_id: str
) -> str | None:
    """Devuelve el ``indexing_target_id`` compatible de menor id (determinista)."""

    matches = sorted(
        target.indexing_target_id
        for target in catalog
        if target.embedding_profile_id == embedding_profile_id
    )
    return matches[0] if matches else None
