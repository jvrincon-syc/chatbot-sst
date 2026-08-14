"""Caso de uso read-only: motores de embedding materializados por proyecto.

Expone el read-model ``ProjectEmbeddingEngine`` como filtro ``(project_id,
motor)`` que acompaña a la matriz de variantes (plan §2.3.2, decisión
2026-08-14). Es de solo lectura y con scope de proyecto: autoriza al operador
(fail-closed), valida ``project_id`` y delega la agregación en el puerto, sin
tocar identidad de artefactos ni el pipeline de build. La dirección de
dependencias es ``infraestructura → aplicación → dominio``: aquí solo vive el
Protocol del puerto; el SQL del join/group-by vive en el adaptador Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.domain.engine_selection import ProjectEmbeddingEngine
from rag_platform.domain.identity import IdentityKind, InvalidIdentity, PlatformId


@runtime_checkable
class ProjectEmbeddingEngineReader(Protocol):
    """Puerto de solo lectura del read-model de motores por proyecto."""

    def list_for_project(
        self, project_id: str
    ) -> Sequence[ProjectEmbeddingEngine]:
        """Devuelve los motores con artefactos materializados del proyecto.

        Args:
            project_id: Valor canónico del proyecto (``proj_...``).

        Returns:
            Los motores agrupados por ``configuration_fingerprint``.
        """


def _sort_key(engine: ProjectEmbeddingEngine) -> tuple[str, str, int, str]:
    """Orden determinista y estable, independiente del adaptador."""

    return (
        engine.provider,
        engine.model,
        engine.dimension,
        engine.configuration_fingerprint,
    )


class ListProjectEmbeddingEnginesUseCase:
    """Lista los motores de embedding materializados de un proyecto."""

    def __init__(
        self,
        *,
        engines: ProjectEmbeddingEngineReader,
        access_policy: PlatformAccessPolicy,
    ) -> None:
        self._engines = engines
        self._access_policy = access_policy

    def execute(
        self, *, project_id: str, actor_id: str
    ) -> tuple[ProjectEmbeddingEngine, ...]:
        """Devuelve los motores de embedding materializados del proyecto.

        Args:
            project_id: Slug técnico del proyecto (sin prefijo ``proj_``).
            actor_id: Operador autenticado; autorizado por la política de acceso.

        Returns:
            Los motores ordenados de forma determinista por
            ``(provider, model, dimension, configuration_fingerprint)``.

        Raises:
            PlatformAccessDenied: Si el actor no es un operador autorizado.
            InvalidIdentity: Si ``project_id`` es vacío o su formato es inválido.
        """

        self._access_policy.require_operator(actor_id=actor_id)

        slug = project_id.strip()
        if not slug:
            raise InvalidIdentity("project_id must not be empty")
        # Construir el PlatformId valida además el formato del slug (fail-closed)
        # y da el valor canónico ``proj_<slug>`` con el que se persiste el scope.
        project_pid = PlatformId(
            kind=IdentityKind.PROJECT,
            value=f"{IdentityKind.PROJECT.value}_{slug}",
        )

        rows = self._engines.list_for_project(project_pid.value)
        return tuple(sorted(rows, key=_sort_key))
