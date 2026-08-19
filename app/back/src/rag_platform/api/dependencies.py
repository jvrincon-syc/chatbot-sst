"""FastAPI dependencies for the RAG platform administrative surface.

Platform routes remain operator/internal, but now the trusted actor is derived
from the authenticated HTTP principal instead of from static server-side actor
configuration. The application layer still sees only ``PlatformActor`` and the
transport-independent ``TrustedPlatformActorProvider`` protocol.
"""

from __future__ import annotations

from fastapi import Request, status

from core.api.http import http_error
from core.feature_flags import FeatureFlags
from core.http_auth import AuthenticatedPrincipal
from rag_platform.application.actor_provider import TrustedPlatformActorProvider
from rag_platform.application.idempotency import IdempotencyStore
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.services import RagPlatformServices
from rag_platform.domain.errors import TrustedActorUnavailable


class AuthenticatedPrincipalActorProvider:
    """Adapt ``AuthenticatedPrincipal`` to the platform actor protocol."""

    def __init__(self, principal: AuthenticatedPrincipal) -> None:
        self._principal = principal

    def current_actor(self) -> PlatformActor:
        return PlatformActor(
            actor_id=self._principal.principal_id,
            project_scope=self._principal.project_scope,
        )


def require_rag_platform_enabled(request: Request) -> None:
    """Gate de feature flag: 503 estable si ``rag_platform_v1`` estÃ¡ apagado."""

    flags: FeatureFlags = request.app.state.feature_flags
    if not flags.rag_platform_v1:
        raise http_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RAG_PLATFORM_V1_DISABLED",
            message="the rag_platform_v1 feature flag is off",
        )


def get_platform_services(request: Request) -> RagPlatformServices:
    """Devuelve la superficie de aplicaciÃ³n de plataforma cableada."""

    return request.app.state.rag_platform


def get_actor_provider(request: Request) -> TrustedPlatformActorProvider:
    """Devuelve el proveedor de actor derivado del principal autenticado."""

    principal = getattr(request.state, "authenticated_principal", None)
    if principal is None:
        raise TrustedActorUnavailable(
            "no authenticated http principal is available for platform requests"
        )
    return AuthenticatedPrincipalActorProvider(principal)


def get_idempotency_store(request: Request) -> IdempotencyStore:
    """Devuelve el almacÃ©n durable de idempotencia (autoridad: PostgreSQL)."""

    return request.app.state.platform_idempotency_store
