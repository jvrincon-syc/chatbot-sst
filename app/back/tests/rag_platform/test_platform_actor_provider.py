"""Fase 7 (Task 4): frontera de actor de confianza server-side.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

El puerto ``TrustedPlatformActorProvider`` permite que el router HTTP entregue un
``PlatformActor`` desde estado autenticado sin que la capa de aplicación conozca
FastAPI. Este test verifica el contrato estructural (Protocol runtime-checkable)
y que un adaptador de confianza devuelve el actor esperado.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import rag_platform.application.actor_provider as actor_provider_module
from rag_platform.application.actor_provider import TrustedPlatformActorProvider
from rag_platform.application.platform_access import PlatformActor


class _StubTrustedActorProvider:
    """Adaptador de confianza de test: deriva el actor de estado ya autenticado."""

    def __init__(self, actor: PlatformActor) -> None:
        self._actor = actor

    def current_actor(self) -> PlatformActor:
        return self._actor


def test_stub_satisface_el_puerto_trusted_actor_provider() -> None:
    provider: TrustedPlatformActorProvider = _StubTrustedActorProvider(
        PlatformActor(actor_id="op-1", project_scope=("proj_demo",))
    )

    assert isinstance(provider, TrustedPlatformActorProvider)


def test_current_actor_devuelve_el_actor_autenticado() -> None:
    actor = PlatformActor(actor_id="op-1", project_scope=("proj_demo",))
    provider = _StubTrustedActorProvider(actor)

    assert provider.current_actor() is actor


def test_el_puerto_no_acopla_fastapi() -> None:
    """La capa de aplicación no importa ``fastapi`` para derivar identidad."""

    source = Path(inspect.getfile(actor_provider_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])

    assert "fastapi" not in imported
