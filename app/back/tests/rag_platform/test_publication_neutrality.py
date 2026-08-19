"""Fase 6: publicación neutral respecto a la lane legacy.

PENDIENTE DE EJECUCIÓN — el entorno local no corre la suite.

Cubre:
- publicar transiciona `VALIDATED → PUBLISHED`,
- publicar sin validar / sin manifiesto / sin permiso falla cerrado,
- el módulo de publicación NO importa `ConsumerScope`, `RetrievalProfile` ni
  `ActivateIndexedBundleUseCase` (test negativo estático),
- publicar no escribe `is_active` ni crea retrieval_profiles (por construcción:
  el caso de uso solo llama a `RagReleaseRepository.update_state`).
"""

from __future__ import annotations

import ast
import inspect
import logging
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pytest

import rag_platform.application.publication_service as publication_module
from rag_platform.application.platform_access import PlatformActor
from rag_platform.application.publication_service import PublishRagReleaseUseCase
from rag_platform.domain.errors import (
    InvalidReleaseTransition,
    PlatformAccessDenied,
    ReleaseManifestFrozen,
)
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.lifecycle import RagRelease, ReleaseState
from rag_platform.infrastructure.in_memory.release_repositories import (
    InMemoryRagReleaseRepository,
)

_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_alpha")
_VARIANT = PlatformId(IdentityKind.RAG_VARIANT, "ragv_bge")
_SNAPSHOT = PlatformId(IdentityKind.CORPUS_SNAPSHOT, "corpus_s1")
_RELEASE = PlatformId(IdentityKind.RAG_RELEASE, "ragr_r1")
_NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


class _AllowAll:
    def require_operator(self, *, actor_id: str) -> None:
        if not actor_id.strip():
            raise PlatformAccessDenied("empty actor")


class _DenyAll:
    def require_operator(self, *, actor_id: str) -> None:
        raise PlatformAccessDenied("denied")


class _NullTx:
    def transaction(self):
        return nullcontext()


class _CountingTx:
    """Cuenta cuántas transacciones de negocio se abren (una sola dueña)."""

    def __init__(self) -> None:
        self.opened = 0

    def transaction(self):
        self.opened += 1
        return nullcontext()


def _release(*, state: ReleaseState, manifest: str | None) -> RagRelease:
    return RagRelease(
        rag_release_id=_RELEASE,
        project_id=_PROJECT,
        rag_variant_id=_VARIANT,
        corpus_snapshot_id=_SNAPSHOT,
        target_binding_key="primary",
        configuration_version=1,
        release_number=1,
        state=state,
        release_manifest_hash=manifest,
        created_by="op-1",
        created_at=_NOW,
    )


def _use_case(release: RagRelease, *, policy=None):
    releases = InMemoryRagReleaseRepository()
    releases.add(release)
    use_case = PublishRagReleaseUseCase(
        releases=releases,
        access_policy=policy or _AllowAll(),
        transactions=_NullTx(),
        logger=logging.getLogger("test.publication"),
    )
    return use_case, releases


def test_publica_release_validada() -> None:
    use_case, releases = _use_case(
        _release(state=ReleaseState.VALIDATED, manifest="a" * 64)
    )

    published = use_case.execute(
        rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1")
    )

    assert published.state is ReleaseState.PUBLISHED
    assert releases.get(_RELEASE).state is ReleaseState.PUBLISHED


def test_publish_posee_una_sola_frontera_transaccional() -> None:
    # El caso de uso es el único dueño de la transacción: el router ya no la
    # envuelve (sin anidamiento de transacciones sobre la misma conexión).
    releases = InMemoryRagReleaseRepository()
    releases.add(_release(state=ReleaseState.VALIDATED, manifest="a" * 64))
    counting = _CountingTx()
    PublishRagReleaseUseCase(
        releases=releases,
        access_policy=_AllowAll(),
        transactions=counting,
        logger=logging.getLogger("test.publication"),
    ).execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))
    assert counting.opened == 1


def test_no_publica_draft_sin_manifiesto() -> None:
    use_case, _ = _use_case(_release(state=ReleaseState.DRAFT, manifest=None))

    with pytest.raises(ReleaseManifestFrozen):
        use_case.execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))


def test_no_publica_desde_estado_no_validado() -> None:
    # Manifiesto presente pero estado PUBLISHED ya: no re-publica (transición inválida).
    use_case, _ = _use_case(
        _release(state=ReleaseState.PUBLISHED, manifest="a" * 64)
    )

    with pytest.raises(InvalidReleaseTransition):
        use_case.execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))


def test_falla_cerrado_sin_permiso() -> None:
    use_case, _ = _use_case(
        _release(state=ReleaseState.VALIDATED, manifest="a" * 64), policy=_DenyAll()
    )

    with pytest.raises(PlatformAccessDenied):
        use_case.execute(rag_release_id=_RELEASE, actor=PlatformActor(actor_id="op-1"))


def test_actor_fuera_de_scope_falla_cerrado() -> None:
    use_case, _ = _use_case(
        _release(state=ReleaseState.VALIDATED, manifest="a" * 64)
    )

    with pytest.raises(PlatformAccessDenied):
        use_case.execute(
            rag_release_id=_RELEASE,
            actor=PlatformActor(actor_id="op-1", project_scope=("proj_beta",)),
        )


def test_modulo_publicacion_no_importa_simbolos_legacy() -> None:
    """Test negativo estático: publicación no acopla la lane legacy (inciso 4)."""

    source = Path(inspect.getfile(publication_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)

    forbidden = {"ConsumerScope", "RetrievalProfile", "ActivateIndexedBundleUseCase"}
    assert not (forbidden & imported)
    # Tampoco accede al atributo `is_active` en código (el docstring puede
    # mencionarlo para documentar la neutralidad; lo que importa es que ningún
    # nodo del AST lea/escriba ese atributo o esos nombres).
    attribute_names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "is_active" not in attribute_names
    assert not (forbidden & (attribute_names | referenced_names))
