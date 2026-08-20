"""Contrato HTTP del intake documental project-aware (Gate 1, Fase 8).

PENDIENTE DE EJECUCIÓN por el operador (el entorno local no corre la suite).

Cubre el upload multipart y el read-model de documentos sobre el adaptador HTTP
delgado:

- ``POST /projects/{id}/documents`` calcula hash/tamaño server-side, persiste los
  bytes bajo la raíz ``raw`` del proyecto y devuelve un ``srev_``;
- ``GET /projects/{id}/documents`` lista revisiones con estado de normalización y
  **sin** rutas físicas;
- fail-closed: fuera de scope 403, proyecto inexistente 404, traversal 400;
- el actor viene solo del principal autenticado (nunca del form).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import build_pipeline_services
from core.feature_flags import FeatureFlags
from core.http_auth import AUTH_CREDENTIALS_JSON_KEY, ConfiguredBearerAuth

GLOBAL_TOKEN = "token-global-op"
ALPHA_TOKEN = "token-alpha-op"


def _authenticator() -> ConfiguredBearerAuth:
    return ConfiguredBearerAuth(
        {
            AUTH_CREDENTIALS_JSON_KEY: (
                "["
                '{"principal_id":"op-1","token":"' + GLOBAL_TOKEN + '"},'
                '{"principal_id":"jose","token":"'
                + ALPHA_TOKEN
                + '","project_scope":["proj_alpha"]}'
                "]"
            )
        }
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(rag_platform_v1=True),
        allow_mock_engine=True,
        http_authenticator=_authenticator(),
    )
    with TestClient(create_app(services=services)) as client:
        client.headers.update(_auth_headers(GLOBAL_TOKEN))
        # data_root lo deriva _platform_data_root como chunks_root.parent == tmp_path.
        yield client, tmp_path


def _create_project(client: TestClient, slug: str) -> None:
    assert (
        client.post(
            "/api/platform/projects",
            json={"project_slug": slug, "display_name": slug.title()},
        ).status_code
        == 201
    )


def _upload(
    client: TestClient,
    slug: str,
    *,
    source_relpath: str,
    content: bytes,
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/api/platform/projects/proj_{slug}/documents",
        files={"file": (source_relpath.split("/")[-1], content, "text/markdown")},
        data={"source_relpath": source_relpath},
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# Upload                                                                       #
# --------------------------------------------------------------------------- #


def test_upload_devuelve_srev_y_persiste_bytes(
    env: tuple[TestClient, Path],
) -> None:
    client, data_root = env
    _create_project(client, "demo")

    response = _upload(
        client, "demo", source_relpath="manuals/guia.md", content=b"# hola\n"
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_document_revision_id"].startswith("srev_")
    assert body["source_relpath"] == "manuals/guia.md"
    assert body["file_size"] == len(b"# hola\n")
    assert body["raw_registered"] is True
    assert body["normalized_registered"] is False
    assert body["processing_status"] == "registered"
    # Bytes persistidos bajo la raíz raw del proyecto (contenida en tmp).
    persisted = data_root / "projects" / "demo" / "raw" / "manuals" / "guia.md"
    assert persisted.read_bytes() == b"# hola\n"


def test_upload_no_expone_rutas_fisicas(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "demo")
    body = _upload(
        client, "demo", source_relpath="a/b.md", content=b"x"
    ).json()
    # StrictModel: ninguna clave de ruta física cruza el contrato.
    assert "artifact_relpath" not in body
    assert not any("/projects/" in str(v) for v in body.values())


def test_upload_traversal_rechazado_y_no_escribe(
    env: tuple[TestClient, Path],
) -> None:
    client, data_root = env
    _create_project(client, "demo")

    response = _upload(
        client, "demo", source_relpath="../escapado.md", content=b"evil"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSAFE_ARTIFACT_PATH"
    assert not (data_root / "projects" / "demo" / "escapado.md").exists()


def test_upload_proyecto_inexistente_404(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    response = _upload(
        client, "nope", source_relpath="a.md", content=b"x"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_upload_fuera_de_scope_403(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "alpha")
    _create_project(client, "beta")

    denied = _upload(
        client,
        "beta",
        source_relpath="a.md",
        content=b"x",
        headers=_auth_headers(ALPHA_TOKEN),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ACCESS_DENIED"


# --------------------------------------------------------------------------- #
# Read-model                                                                   #
# --------------------------------------------------------------------------- #


def test_list_documents_vacio_ok(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "demo")
    response = client.get("/api/platform/projects/proj_demo/documents")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_list_documents_muestra_subida(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "demo")
    srev = _upload(
        client, "demo", source_relpath="manuals/guia.md", content=b"hola"
    ).json()["source_document_revision_id"]

    items = client.get("/api/platform/projects/proj_demo/documents").json()["items"]

    assert [i["source_document_revision_id"] for i in items] == [srev]
    assert items[0]["normalized_registered"] is False
    assert items[0]["processing_status"] == "registered"


def test_list_documents_orden_estable(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "demo")
    _upload(client, "demo", source_relpath="a.md", content=b"aaa")
    _upload(client, "demo", source_relpath="b.md", content=b"bbb")

    first = client.get("/api/platform/projects/proj_demo/documents").json()["items"]
    second = client.get("/api/platform/projects/proj_demo/documents").json()["items"]
    # Orden determinista entre lecturas (sobrevive a refresh de la GUI).
    assert [i["source_relpath"] for i in first] == [
        i["source_relpath"] for i in second
    ]
    assert {i["source_relpath"] for i in first} == {"a.md", "b.md"}


def test_list_documents_fuera_de_scope_403(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "beta")
    denied = client.get(
        "/api/platform/projects/proj_beta/documents",
        headers=_auth_headers(ALPHA_TOKEN),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ACCESS_DENIED"


# --------------------------------------------------------------------------- #
# Normalize (validación/autorización antes del motor; el happy-path corre el   #
# engine y se cubre por el CLI/corpus, no en la suite rápida)                  #
# --------------------------------------------------------------------------- #


def test_normalize_exige_rag_variant_id(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "demo")
    response = client.post(
        "/api/platform/projects/proj_demo/normalize",
        json={"document_revision_ids": ["srev_x"]},
    )
    assert response.status_code == 422


def test_normalize_exige_al_menos_una_revision(
    env: tuple[TestClient, Path],
) -> None:
    client, _ = env
    _create_project(client, "demo")
    response = client.post(
        "/api/platform/projects/proj_demo/normalize",
        json={"rag_variant_id": "ragv_x", "document_revision_ids": []},
    )
    assert response.status_code == 422


def test_normalize_proyecto_inexistente_404(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    response = client.post(
        "/api/platform/projects/proj_nope/normalize",
        json={"rag_variant_id": "ragv_x", "document_revision_ids": ["srev_x"]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_normalize_fuera_de_scope_403(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    _create_project(client, "beta")
    denied = client.post(
        "/api/platform/projects/proj_beta/normalize",
        json={"rag_variant_id": "ragv_x", "document_revision_ids": ["srev_x"]},
        headers=_auth_headers(ALPHA_TOKEN),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PLATFORM_ACCESS_DENIED"
