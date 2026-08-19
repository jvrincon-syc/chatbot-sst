"""Dependencias FastAPI y adaptador de actor de confianza (Fase 7).

La capa API resuelve, desde el estado ya cableado en ``app.state``, la superficie
de aplicación (``RagPlatformServices``), el proveedor de actor de confianza y el
almacén de idempotencia. El router **nunca** construye repositorios concretos ni
lee variables de entorno directamente: toda autoridad llega ya resuelta.

``ConfiguredPlatformActorProvider`` es el adaptador de confianza de Fase 7:
deriva el ``PlatformActor`` de configuración server-side (no de datos del
cliente). Es el único punto que conoce las claves de configuración del operador;
una futura transición a SSO/OIDC solo reemplaza este proveedor sin tocar rutas ni
casos de uso.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request, status

from core.api.http import http_error
from core.feature_flags import FeatureFlags
from rag_platform.application.actor_provider import TrustedPlatformActorProvider
from rag_platform.application.idempotency import IdempotencyStore
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.services import RagPlatformServices
from rag_platform.domain.errors import TrustedActorUnavailable

#: Clave de configuración del actor de confianza (identidad server-side).
ACTOR_ID_KEY = "SST_PLATFORM_ACTOR_ID"
#: Clave del scope de proyectos (lista separada por comas). Vacía/ausente =
#: operador global sin restricción de proyecto.
ACTOR_PROJECT_SCOPE_KEY = "SST_PLATFORM_ACTOR_PROJECT_SCOPE"


class ConfiguredPlatformActorProvider:
    """Provee un ``PlatformActor`` desde configuración server-side de confianza.

    Fail-closed: si no hay un ``actor_id`` configurado no fabrica identidad; lanza
    ``TrustedActorUnavailable`` para que la API se abstenga. No lee el body, la
    query ni headers controlados por el cliente.
    """

    def __init__(self, config: Mapping[str, str]) -> None:
        self._actor_id = (config.get(ACTOR_ID_KEY) or "").strip()
        raw_scope = (config.get(ACTOR_PROJECT_SCOPE_KEY) or "").strip()
        # Scope vacío -> operador global (None). Una lista explícita restringe.
        scope = tuple(
            item.strip() for item in raw_scope.split(",") if item.strip()
        )
        self._project_scope: tuple[str, ...] | None = scope or None

    def current_actor(self) -> PlatformActor:
        """Devuelve el actor de confianza o falla cerrado si no está configurado."""

        if not self._actor_id:
            raise TrustedActorUnavailable(
                "no trusted platform actor is configured server-side"
            )
        return PlatformActor(
            actor_id=self._actor_id, project_scope=self._project_scope
        )


def require_rag_platform_enabled(request: Request) -> None:
    """Gate de feature flag: 503 estable si ``rag_platform_v1`` está apagado."""

    flags: FeatureFlags = request.app.state.feature_flags
    if not flags.rag_platform_v1:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RAG_PLATFORM_V1_DISABLED",
            message="the rag_platform_v1 feature flag is off",
        )


def get_platform_services(request: Request) -> RagPlatformServices:
    """Devuelve la superficie de aplicación de plataforma cableada."""

    return request.app.state.rag_platform


def get_actor_provider(request: Request) -> TrustedPlatformActorProvider:
    """Devuelve el proveedor de actor de confianza cableado."""

    return request.app.state.platform_actor_provider


def get_idempotency_store(request: Request) -> IdempotencyStore:
    """Devuelve el almacén durable de idempotencia (autoridad: PostgreSQL)."""

    return request.app.state.platform_idempotency_store


def get_platform_transactions(request: Request) -> object:
    """Devuelve el ``TransactionManager`` de negocio (UoW de las mutaciones)."""

    return request.app.state.platform_transactions
