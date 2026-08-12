"""Actor de plataforma y autorización con scope de proyecto (Fase 6).

Extiende el ``PlatformAccessPolicy`` existente (``context.py``, autoriza operador
por ``actor_id``) con un actor tipado y una guarda scoped por proyecto, sin
duplicar el Protocol ni romper sus consumidores actuales.

``require_project_operator`` es fail-closed: primero exige operador autorizado
(delegando en el policy existente) y luego, si el actor declara un scope de
proyectos, exige que el ``project_id`` objetivo esté dentro de ese scope.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag_platform.application.context import PlatformAccessPolicy
from rag_platform.domain.errors import PlatformAccessDenied
from rag_platform.domain.identity import PlatformId


@dataclass(frozen=True)
class PlatformActor:
    """Actor autenticado que opera sobre la plataforma.

    ``project_scope`` es la allowlist de proyectos que el actor puede administrar.
    ``None`` significa operador global (sin restricción de proyecto); una tupla
    vacía significa un actor sin ningún proyecto permitido (fail-closed).
    """

    actor_id: str
    project_scope: tuple[str, ...] | None = None


def require_project_operator(
    *,
    policy: PlatformAccessPolicy,
    actor: PlatformActor,
    project_id: PlatformId,
) -> None:
    """Autoriza a ``actor`` a operar sobre ``project_id`` (fail-closed).

    Args:
        policy: Política base que valida que el actor es un operador autorizado.
        actor: Actor autenticado y su scope de proyectos.
        project_id: Proyecto objetivo de la operación.

    Raises:
        PlatformAccessDenied: Si el actor no es operador o el proyecto está fuera
            de su scope.
    """

    policy.require_operator(actor_id=actor.actor_id)
    if actor.project_scope is not None and project_id.value not in actor.project_scope:
        raise PlatformAccessDenied(
            f"actor {actor.actor_id!r} is not scoped to project {project_id.value}"
        )
