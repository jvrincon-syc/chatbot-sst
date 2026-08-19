"""Contrato HTTP de la plataforma RAG (Fase 7) + semántica de idempotencia.

PENDIENTE DE EJECUCIÓN por el operador (el entorno local no corre la suite).

Cubre el adaptador HTTP delgado sobre ``services.rag_platform.*``:

- superficie de proyectos/configuración/variantes vía ``TestClient`` in-memory;
- actor **solo** desde el proveedor de confianza (nunca del body): un ``actor_id``
  en el payload se rechaza (422) y la falta de actor de confianza falla cerrado;
- gate de feature flag (503 cuando ``rag_platform_v1`` está apagado);
- traducción central de ``RagPlatformError`` al envelope compartido;
- idempotencia durable a nivel ``IdempotencyGuard`` (replay no re-ejecuta,
  fingerprint distinto = conflicto, RESERVED concurrente no arranca segundo build).
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import build_pipeline_services
from core.feature_flags import FeatureFlags
from rag_platform.api.dependencies import ConfiguredPlatformActorProvider
from rag_platform.application.idempotency import (
    IdempotencyGuard,
    IdempotencyKeyConflict,
    IdempotencyOperationInProgress,
    IdempotencyRecord,
    IdempotencyStatus,
    idempotency_request_fingerprint,
)
from rag_platform.application.platform_access import PlatformActor
from rag_platform.infrastructure.in_memory.idempotency import InMemoryIdempotencyStore
from datetime import datetime, timezone


class _StubActorProvider:
    """Proveedor de confianza de test: devuelve un actor server-side fijo."""

    def __init__(self, actor: PlatformActor) -> None:
        self._actor = actor

    def current_actor(self) -> PlatformActor:
        return self._actor


def _build_client(
    tmp_path: Path,
    *,
    rag_platform_v1: bool,
    actor_provider: object,
) -> TestClient:
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(rag_platform_v1=rag_platform_v1),
        allow_mock_engine=True,
        platform_actor_provider=actor_provider,
    )
    return TestClient(create_app(services=services))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    provider = _StubActorProvider(PlatformActor(actor_id="op-1", project_scope=None))
    with _build_client(tmp_path, rag_platform_v1=True, actor_provider=provider) as c:
        yield c


@pytest.fixture
def flag_off_client(tmp_path: Path) -> Iterator[TestClient]:
    provider = _StubActorProvider(PlatformActor(actor_id="op-1", project_scope=None))
    with _build_client(tmp_path, rag_platform_v1=False, actor_provider=provider) as c:
        yield c


@pytest.fixture
def no_actor_client(tmp_path: Path) -> Iterator[TestClient]:
    # Configuración de operador ausente: el proveedor falla cerrado.
    provider = ConfiguredPlatformActorProvider({})
    with _build_client(tmp_path, rag_platform_v1=True, actor_provider=provider) as c:
        yield c


def _create_project(client: TestClient, slug: str = "demo") -> dict:
    response = client.post(
        "/api/platform/projects",
        json={"project_slug": slug, "display_name": "Demo"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Superficie de proyectos / configuración                                      #
# --------------------------------------------------------------------------- #


def test_list_projects_vacio_ok(client: TestClient) -> None:
    response = client.get("/api/platform/projects")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_crear_y_leer_proyecto(client: TestClient) -> None:
    created = _create_project(client, "demo")
    assert created["project_id"] == "proj_demo"

    fetched = client.get("/api/platform/projects/proj_demo")
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "Demo"
    assert fetched.json()["configuration"]["version"] == 1


def test_actualizar_display_name(client: TestClient) -> None:
    _create_project(client, "demo")
    response = client.patch(
        "/api/platform/projects/proj_demo",
        json={"display_name": "Renombrado"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Renombrado"
    assert response.json()["project_id"] == "proj_demo"


def test_leer_configuracion_vigente(client: TestClient) -> None:
    _create_project(client, "demo")
    response = client.get("/api/platform/projects/proj_demo/configuration")
    assert response.status_code == 200
    assert response.json()["version"] == 1


def test_variant_matrix_vacia_ok(client: TestClient) -> None:
    _create_project(client, "demo")
    response = client.get("/api/platform/projects/proj_demo/variant-matrix")
    assert response.status_code == 200
    assert response.json() == []


# --------------------------------------------------------------------------- #
# Seguridad: actor, flag, IDs                                                  #
# --------------------------------------------------------------------------- #


def test_actor_id_en_body_se_rechaza(client: TestClient) -> None:
    """La identidad nunca viene del body: un ``actor_id`` extra se rechaza (422)."""

    response = client.post(
        "/api/platform/projects",
        json={
            "project_slug": "demo",
            "display_name": "Demo",
            "actor_id": "atacante",
        },
    )
    assert response.status_code == 422


def test_flag_apagado_devuelve_503(flag_off_client: TestClient) -> None:
    response = flag_off_client.get("/api/platform/projects")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RAG_PLATFORM_V1_DISABLED"


def test_actor_de_confianza_ausente_falla_cerrado(no_actor_client: TestClient) -> None:
    # Lectura sin actor funciona; una mutación exige actor de confianza.
    assert no_actor_client.get("/api/platform/projects").status_code == 200
    response = no_actor_client.post(
        "/api/platform/projects",
        json={"project_slug": "demo", "display_name": "Demo"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TRUSTED_ACTOR_UNAVAILABLE"


def test_proyecto_inexistente_404_traducido(client: TestClient) -> None:
    response = client.get("/api/platform/projects/proj_nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_id_malformado_422(client: TestClient) -> None:
    response = client.get("/api/platform/projects/no-es-un-id")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PLATFORM_ID"


# --------------------------------------------------------------------------- #
# Idempotencia sobre comandos de release (nivel HTTP)                          #
# --------------------------------------------------------------------------- #


def test_build_exige_idempotency_key(client: TestClient) -> None:
    """Sin ``Idempotency-Key`` la mutación de release se rechaza (422)."""

    response = client.post("/api/platform/releases/ragr_x/build")
    assert response.status_code == 422


def test_build_release_inexistente_falla_y_replay_lo_surface(
    client: TestClient,
) -> None:
    headers = {"Idempotency-Key": "k-build-1"}
    first = client.post("/api/platform/releases/ragr_missing/build", headers=headers)
    assert first.status_code == 404
    assert first.json()["error"]["code"] == "RAG_RELEASE_NOT_FOUND"

    # Replay de un intento fallido: no devuelve 200 vacío enmascarando el error.
    replay = client.post("/api/platform/releases/ragr_missing/build", headers=headers)
    assert replay.status_code >= 400
    assert replay.json()["error"]["code"] == "IDEMPOTENT_OPERATION_FAILED"


# --------------------------------------------------------------------------- #
# Idempotencia (nivel guard, determinista)                                     #
# --------------------------------------------------------------------------- #


def _actor_id() -> str:
    return "op-1"


def test_guard_replay_no_reejecuta_la_operacion() -> None:
    store = InMemoryIdempotencyStore()
    guard = IdempotencyGuard(store=store)
    calls = {"n": 0}

    def _op() -> dict:
        calls["n"] += 1
        return {"ok": True}

    def _run():
        return guard.run(
            idempotency_key="k1",
            action="publish",
            resource_id="ragr_a",
            actor_id=_actor_id(),
            response_status=200,
            operation=_op,
        )

    first = _run()
    second = _run()
    assert calls["n"] == 1
    assert first.replayed is False
    assert second.replayed is True
    assert second.result_json == {"ok": True}


def test_guard_conflicto_por_fingerprint_distinto() -> None:
    store = InMemoryIdempotencyStore()
    guard = IdempotencyGuard(store=store)
    guard.run(
        idempotency_key="k1",
        action="publish",
        resource_id="ragr_a",
        actor_id=_actor_id(),
        response_status=200,
        operation=lambda: {"ok": True},
    )
    # Misma clave, recurso distinto (fingerprint distinto): fail-closed.
    with pytest.raises(IdempotencyKeyConflict):
        guard.run(
            idempotency_key="k1",
            action="publish",
            resource_id="ragr_b",
            actor_id=_actor_id(),
            response_status=200,
            operation=lambda: {"ok": True},
        )


def test_guard_scoped_por_principal_otro_actor_no_recibe_replay() -> None:
    """Misma clave, actor distinto: conflicto (no entrega el replay del primero)."""

    store = InMemoryIdempotencyStore()
    guard = IdempotencyGuard(store=store)
    guard.run(
        idempotency_key="k1",
        action="publish",
        resource_id="ragr_a",
        actor_id="jose",
        response_status=200,
        operation=lambda: {"ok": True},
    )
    with pytest.raises(IdempotencyKeyConflict):
        guard.run(
            idempotency_key="k1",
            action="publish",
            resource_id="ragr_a",
            actor_id="maria",
            response_status=200,
            operation=lambda: {"ok": True},
        )


def test_guard_reserva_en_curso_no_arranca_segundo_build() -> None:
    store = InMemoryIdempotencyStore()
    key = "k1"
    action = "build"
    resource_id = "ragr_a"
    # Simula una ejecución concurrente que ya reservó y sigue RESERVED.
    store.reserve(
        IdempotencyRecord(
            key_hash=sha256(key.encode("utf-8")).hexdigest(),
            action=action,
            resource_id=resource_id,
            request_fingerprint=idempotency_request_fingerprint(
                action=action, resource_id=resource_id, actor_id=_actor_id()
            ),
            actor_id=_actor_id(),
            status=IdempotencyStatus.RESERVED,
            created_at=datetime.now(timezone.utc),
        )
    )
    calls = {"n": 0}

    def _op() -> dict:
        calls["n"] += 1
        return {"ok": True}

    with pytest.raises(IdempotencyOperationInProgress):
        IdempotencyGuard(store=store).run(
            idempotency_key=key,
            action=action,
            resource_id=resource_id,
            actor_id=_actor_id(),
            response_status=200,
            operation=_op,
        )
    assert calls["n"] == 0
