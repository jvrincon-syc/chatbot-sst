"""Frontera de actor de confianza para la superficie de plataforma (Fase 7).

El router HTTP nunca inventa autorización ni acepta ``actor_id`` de un body o
header no autenticado (invariante §1 del plan). En su lugar, el adaptador HTTP
implementa ``TrustedPlatformActorProvider`` a partir de estado server-side ya
autenticado y entrega un ``PlatformActor`` tipado a los casos de uso.

La capa de aplicación **no** importa ``fastapi.Request`` ni ningún transporte:
solo declara el puerto. El adaptador concreto (Fase 7/8) vive en la capa API.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_platform.application.platform_access import PlatformActor


@runtime_checkable
class TrustedPlatformActorProvider(Protocol):
    """Provee el ``PlatformActor`` autenticado del borde server-side de confianza."""

    def current_actor(self) -> PlatformActor:
        """Devuelve el actor autenticado; nunca deriva identidad de datos del cliente."""
