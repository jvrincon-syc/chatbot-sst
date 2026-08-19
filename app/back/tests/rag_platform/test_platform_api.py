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
from core.http_auth import AUTH_CREDENTIALS_JSON_KEY, ConfiguredBearerAuth
from core.feature_flags import FeatureFlags
from rag_platform.application.idempotency import (
    IdempotencyGuard,
    IdempotencyKeyConflict,
    IdempotencyOperationInProgress,
    IdempotencyRecord,
    IdempotencyStatus,
    idempotency_request_fingerprint,
)
from rag_platform.infrastructure.in_memory.idempotency import InMemoryIdempotencyStore
from datetime import datetime, timezone

GLOBAL_TOKEN = "token-global-op"
ALPHA_TOKEN = "token-alpha-op"
EMPTY_SCOPE_TOKEN = "token-empty-scope"


def _authenticator() -> ConfiguredBearerAuth:
    return ConfiguredBearerAuth(
        {
            AUTH_CREDENTIALS_JSON_KEY: (
                "["
                '{"principal_id":"op-1","token":"'
                + GLOBAL_TOKEN
                + '"},'
                '{"principal_id":"jose","token":"'
                + ALPHA_TOKEN
                + '","project_scope":["proj_alpha"]},'
                '{"principal_id":"jose","token":"'
                + EMPTY_SCOPE_TOKEN
                + '","project_scope":[]}'
                "]"
            )
        }
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_client(
    tmp_path: Path,
    *,
    rag_platform_v1: bool,
    authenticator: ConfiguredBearerAuth | None,
) -> TestClient:
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(rag_platform_v1=rag_platform_v1),
        allow_mock_engine=True,
        http_authenticator=authenticator,
    )
    return TestClient(create_app(services=services))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _build_client(
        tmp_path, rag_platform_v1=True, authenticator=_authenticator()
    ) as c:
        c.headers.update(_auth_headers(GLOBAL_TOKEN))
        yield c


@pytest.fixture
def flag_off_client(tmp_path: Path) -> Iterator[TestClient]:
    with _build_client(
        tmp_path, rag_platform_v1=False, authenticator=_authenticator()
    ) as c:
        c.headers.update(_auth_headers(GLOBAL_TOKEN))
        yield c


@pytest.fixture
def unauthenticated_client(tmp_path: Path) -> Iterator[TestClient]:
    # Configuración de operador ausente: el proveedor falla cerrado.
    with _build_client(
        tmp_path, rag_platform_v1=True, authenticator=_authenticator()
    ) as c:
        yield c


@pytest.fixture
def auth_not_configured_client(tmp_path: Path) -> Iterator[TestClient]:
    with _build_client(tmp_path, rag_platform_v1=True, authenticator=None) as c:
        yield c


@pytest.fixture
def scoped_client(tmp_path: Path) -> Iterator[TestClient]:
    with _build_client(
        tmp_path, rag_platform_v1=True, authenticator=_authenticator()
    ) as c:
        c.headers.update(_auth_headers(GLOBAL_TOKEN))
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


def test_create_project_rechaza_target_bindings_inyectados(client: TestClient) -> None:
    """El DTO HTTP no acepta bindings/target físico: un intento se rechaza (422)."""

    response = client.post(
        "/api/platform/projects",
        json={
            "project_slug": "demo",
            "display_name": "Demo",
            "target_bindings": [
                {
                    "binding_key": "primary",
                    "indexing_target_id": "idx_vec_hacked",
                    "embedding_profile_id": "bge-m3",
                }
            ],
        },
    )
    assert response.status_code == 422


def test_patch_configuracion_rechaza_target_bindings_inyectados(
    client: TestClient,
) -> None:
    _create_project(client, "demo")
    response = client.patch(
        "/api/platform/projects/proj_demo/configuration",
        json={
            "corpus_organization_policy": "source-folders-v1",
            "target_bindings": [
                {
                    "binding_key": "primary",
                    "indexing_target_id": "idx_vec_hacked",
                    "embedding_profile_id": "bge-m3",
                }
            ],
        },
    )
    assert response.status_code == 422


def test_flag_apagado_devuelve_503(flag_off_client: TestClient) -> None:
    response = flag_off_client.get("/api/platform/projects")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "RAG_PLATFORM_V1_DISABLED"


def test_exige_bearer_token_en_plataforma(
    unauthenticated_client: TestClient,
) -> None:
    # Sin actor de confianza, tanto lecturas como mutaciones fallan cerrado: la
    # autorización por scope exige un ``PlatformActor`` también en las GET.
    read = unauthenticated_client.get("/api/platform/projects")
    assert read.status_code == 401
    assert read.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"
    write = unauthenticated_client.post(
        "/api/platform/projects",
        json={"project_slug": "demo", "display_name": "Demo"},
    )
    assert write.status_code == 401
    assert write.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"


def test_falla_cerrado_si_auth_http_no_esta_configurada(
    auth_not_configured_client: TestClient,
) -> None:
    response = auth_not_configured_client.get("/api/platform/projects")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "HTTP_AUTH_NOT_CONFIGURED"


def test_token_bearer_invalido_da_401(
    unauthenticated_client: TestClient,
) -> None:
    # Un bearer presente pero no registrado se rechaza (constant-time compare).
    response = unauthenticated_client.get(
        "/api/platform/projects",
        headers=_auth_headers("token-que-no-existe"),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HTTP_AUTH_INVALID_CREDENTIALS"
    assert response.headers.get("WWW-Authenticate") == "Bearer"


# --------------------------------------------------------------------------- #
# Task 1: scope de lectura (fail-closed cross-project)                          #
# --------------------------------------------------------------------------- #


def _seed_two_projects(client: TestClient) -> TestClient:
    """Siembra ``proj_alpha`` y ``proj_beta`` como operador global."""
    for slug in ("alpha", "beta"):
        assert (
            client.post(
                "/api/platform/projects",
                json={"project_slug": slug, "display_name": slug.title()},
            ).status_code
            == 201
        )
    return client


def test_list_projects_global_ve_todo(
    scoped_client: TestClient,
) -> None:
    client = _seed_two_projects(scoped_client)
    ids = {p["project_id"] for p in client.get("/api/platform/projects").json()["items"]}
    assert ids == {"proj_alpha", "proj_beta"}


def test_list_projects_scoped_ve_solo_los_suyos(
    scoped_client: TestClient,
) -> None:
    client = _seed_two_projects(scoped_client)
    ids = {
        p["project_id"]
        for p in client.get(
            "/api/platform/projects",
            headers=_auth_headers(ALPHA_TOKEN),
        ).json()["items"]
    }
    assert ids == {"proj_alpha"}


def test_list_projects_scope_vacio_ve_cero(
    scoped_client: TestClient,
) -> None:
    client = _seed_two_projects(scoped_client)
    assert (
        client.get(
            "/api/platform/projects",
            headers=_auth_headers(EMPTY_SCOPE_TOKEN),
        ).json()["items"]
        == []
    )


def test_get_proyecto_en_scope_ok_fuera_de_scope_403(
    scoped_client: TestClient,
) -> None:
    client = _seed_two_projects(scoped_client)
    assert (
        client.get(
            "/api/platform/projects/proj_alpha",
            headers=_auth_headers(ALPHA_TOKEN),
        ).status_code
        == 200
    )
    denied = client.get(
        "/api/platform/projects/proj_beta",
        headers=_auth_headers(ALPHA_TOKEN),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ACCESS_DENIED"


def test_get_configuracion_y_matriz_fuera_de_scope_403(
    scoped_client: TestClient,
) -> None:
    client = _seed_two_projects(scoped_client)
    assert (
        client.get(
            "/api/platform/projects/proj_beta/configuration",
            headers=_auth_headers(ALPHA_TOKEN),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/platform/projects/proj_beta/variant-matrix",
            headers=_auth_headers(ALPHA_TOKEN),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/platform/projects/proj_beta/variants",
            headers=_auth_headers(ALPHA_TOKEN),
        ).status_code
        == 403
    )


def test_get_ignora_actor_de_header_o_query(
    scoped_client: TestClient,
) -> None:
    """La identidad viene solo del proveedor de confianza: header/query se ignoran."""

    client = _seed_two_projects(scoped_client)
    denied = client.get(
        "/api/platform/projects/proj_beta?actor_id=superuser",
        headers={
            **_auth_headers(ALPHA_TOKEN),
            "X-Actor-Id": "superuser",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ACCESS_DENIED"


def test_slug_de_body_invalido_da_422_no_500(client: TestClient) -> None:
    """Un ``project_slug`` malformado construye un ``PlatformId`` inválido dentro
    del caso de uso: el handler central lo traduce a 422, nunca 500."""

    response = client.post(
        "/api/platform/projects",
        json={"project_slug": "Mi Proyecto", "display_name": "Demo"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PLATFORM_ID"


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


def test_guard_reason_material_cambia_fingerprint_de_retire() -> None:
    """Misma clave/actor/recurso pero ``reason`` distinto: conflicto (no replay)."""

    store = InMemoryIdempotencyStore()
    guard = IdempotencyGuard(store=store)
    guard.run(
        idempotency_key="k1",
        action="retire",
        resource_id="ragr_a",
        actor_id="op-1",
        response_status=200,
        operation=lambda: {"ok": True},
        request_fields={"reason": "deprecated"},
    )
    with pytest.raises(IdempotencyKeyConflict):
        guard.run(
            idempotency_key="k1",
            action="retire",
            resource_id="ragr_a",
            actor_id="op-1",
            response_status=200,
            operation=lambda: {"ok": True},
            request_fields={"reason": "security incident"},
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
