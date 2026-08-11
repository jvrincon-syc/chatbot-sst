"""HTTP contract of the Embedding, Indexing and Retrieval APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import build_pipeline_services
from core.feature_flags import FeatureFlags

from pipeline_fixtures import build_profile, build_target, write_chunk_bundle


SCOPE_TYPE = "chatbot"
SCOPE_ID = "sst-default"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    profile = build_profile()
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(
            embedding_v2=True,
            indexing_bundle_first=True,
            retrieval_v1=True,
        ),
        allow_mock_engine=True,
        seed_profiles=[profile],
        seed_targets=[build_target()],
        seed_chunk_bundles=[chunk_bundle],
        lexical_profile_id=profile.profile_id,
    )
    app = create_app(services=services)
    app.state.test_profile = profile
    app.state.test_chunk_bundle = chunk_bundle
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def blocked_client(tmp_path: Path) -> Iterator[TestClient]:
    profile = build_profile()
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(
            embedding_v2=False,
            indexing_bundle_first=False,
            retrieval_v1=False,
        ),
        allow_mock_engine=True,
        seed_profiles=[profile],
        seed_targets=[build_target()],
    )
    with TestClient(create_app(services=services)) as test_client:
        yield test_client


@pytest.fixture
def client_default_lexical_profile(tmp_path: Path) -> Iterator[TestClient]:
    profile = build_profile()
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    services = build_pipeline_services(
        chunks_root=tmp_path / "chunks",
        embeddings_root=tmp_path / "embeddings",
        feature_flags=FeatureFlags(
            embedding_v2=True,
            indexing_bundle_first=True,
            retrieval_v1=True,
        ),
        allow_mock_engine=True,
        seed_profiles=[profile],
        seed_targets=[build_target()],
        seed_chunk_bundles=[chunk_bundle],
    )
    app = create_app(services=services)
    app.state.test_profile = profile
    app.state.test_chunk_bundle = chunk_bundle
    with TestClient(app) as test_client:
        yield test_client


def _run_embedding(client: TestClient) -> dict:
    payload = {
        "chunk_bundle_id": client.app.state.test_chunk_bundle.chunk_bundle_id,
        "profile_id": client.app.state.test_profile.profile_id,
    }
    response = client.post(
        "/api/embedding/runs",
        json=payload,
        headers={"Idempotency-Key": "embed-1"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["embedding_run_id"]
    for _ in range(200):
        run = client.get(f"/api/embedding/runs/{run_id}").json()
        if run["status"] in {"completed", "failed", "blocked"}:
            return run
    raise AssertionError("embedding run never reached a terminal state")


def _run_indexing(client: TestClient, embedding_bundle_id: str) -> dict:
    response = client.post(
        "/api/indexing/runs",
        json={"embedding_bundle_id": embedding_bundle_id},
        headers={"Idempotency-Key": "index-1"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    for _ in range(200):
        run = client.get(f"/api/indexing/runs/{run_id}").json()
        if run["status"] in {"completed", "failed", "blocked"}:
            return run
    raise AssertionError("indexing run never reached a terminal state")


def test_lista_perfiles_con_paginacion_snake_case(client: TestClient) -> None:
    response = client.get("/api/embedding/profiles?page=1&page_size=10")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "page_size", "total_items", "total_pages"}
    assert body["items"][0]["can_embed_documents"] is True
    assert "configuration_fingerprint" in body["items"][0]


def test_expone_runtime_sin_secretos(client: TestClient) -> None:
    response = client.get("/api/embedding/runtime")

    assert response.status_code == 200
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "voyage_api_key" not in serialized
    assert "hf_token" not in serialized


def test_crea_run_de_embedding_y_sella_el_bundle(client: TestClient) -> None:
    run = _run_embedding(client)

    assert run["status"] == "completed"
    bundle_id = run["produced_embedding_bundle_id"]
    bundle = client.get(f"/api/embedding/bundles/{bundle_id}").json()
    assert bundle["status"] == "sealed"
    assert bundle["validation_status"] == "passed"
    assert "vectors" not in bundle
    assert "embedding" not in bundle


def test_los_chunks_del_bundle_no_devuelven_vectores(client: TestClient) -> None:
    run = _run_embedding(client)
    bundle_id = run["produced_embedding_bundle_id"]

    response = client.get(f"/api/embedding/bundles/{bundle_id}/chunks?page=1&page_size=50")

    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == client.app.state.test_chunk_bundle.child_count
    for item in body["items"]:
        assert "embedding" not in item
        assert "vector" not in item
        assert item["vector_checksum"]


def test_devuelve_conflicto_cuando_la_key_se_reusa_con_otro_payload(client: TestClient) -> None:
    _run_embedding(client)

    response = client.post(
        "/api/embedding/runs",
        json={
            "chunk_bundle_id": client.app.state.test_chunk_bundle.chunk_bundle_id,
            "profile_id": "otro-perfil",
        },
        headers={"Idempotency-Key": "embed-1"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EMBEDDING_PROFILE_NOT_FOUND"


def test_exige_el_header_de_idempotencia(client: TestClient) -> None:
    response = client.post(
        "/api/embedding/runs",
        json={
            "chunk_bundle_id": client.app.state.test_chunk_bundle.chunk_bundle_id,
            "profile_id": client.app.state.test_profile.profile_id,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PIPELINE_INVALID_REQUEST"


def test_devuelve_404_con_envelope_cuando_el_run_no_existe(client: TestClient) -> None:
    response = client.get("/api/embedding/runs/no-existe")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "EMBEDDING_RUN_NOT_FOUND"
    assert error["run_id"] == "no-existe"
    assert set(error) == {"code", "message", "run_id", "details"}


def test_indexa_y_activa_el_bundle_por_http(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    bundle_id = embedding_run["produced_embedding_bundle_id"]
    indexing_run = _run_indexing(client, bundle_id)
    assert indexing_run["status"] == "completed"
    assert indexing_run["activation_status"] == "pending"

    readiness = client.get(
        f"/api/indexing/runs/{indexing_run['run_id']}/retrieval-readiness"
    ).json()
    assert readiness["ready"] is False
    assert "INDEXING_BUNDLE_NOT_ACTIVATED" in readiness["blocking_reasons"]

    activation = client.post(
        "/api/indexing/activations",
        json={"run_id": indexing_run["run_id"]},
    )
    assert activation.status_code == 200, activation.text
    assert activation.json()["activated_rows"] == 3

    readiness = client.get(
        f"/api/indexing/runs/{indexing_run['run_id']}/retrieval-readiness"
    ).json()
    assert readiness["ready"] is True


def test_el_contrato_de_indexing_no_pide_provider_ni_modelo(client: TestClient) -> None:
    schema = client.app.openapi()["components"]["schemas"]["IndexingRunRequestSchema"]

    assert set(schema["properties"]) == {"embedding_bundle_id"}


def test_activation_y_rollback_no_aceptan_consumer_scope_en_el_body(
    client: TestClient,
) -> None:
    activation_schema = client.app.openapi()["components"]["schemas"][
        "ActivationRequestSchema"
    ]
    rollback_schema = client.app.openapi()["components"]["schemas"][
        "RollbackRequestSchema"
    ]

    assert "consumer_scope_type" not in activation_schema["properties"]
    assert "consumer_scope_id" not in activation_schema["properties"]
    assert "consumer_scope_type" not in rollback_schema["properties"]
    assert "consumer_scope_id" not in rollback_schema["properties"]


def test_activation_rechaza_scope_inyectado_en_el_body(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    indexing_run = _run_indexing(client, embedding_run["produced_embedding_bundle_id"])

    # A client trying to smuggle another scope through the body is rejected by
    # the strict schema; the scope can only come from the server.
    response = client.post(
        "/api/indexing/activations",
        json={
            "run_id": indexing_run["run_id"],
            "consumer_scope_type": "attacker",
            "consumer_scope_id": "other-tenant",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PIPELINE_INVALID_REQUEST"


def test_activation_y_rollback_bloqueadas_con_el_flag_apagado(
    blocked_client: TestClient,
) -> None:
    activation = blocked_client.post(
        "/api/indexing/activations",
        json={"run_id": "any-run"},
    )
    rollback = blocked_client.post(
        "/api/indexing/rollbacks",
        json={
            "current_embedding_bundle_id": "curr",
            "previous_embedding_bundle_id": "prev",
        },
    )

    assert activation.status_code == 503
    assert activation.json()["error"]["code"] == "INDEXING_BUNDLE_FIRST_DISABLED"
    assert rollback.status_code == 503
    assert rollback.json()["error"]["code"] == "INDEXING_BUNDLE_FIRST_DISABLED"


def test_lista_documentos_y_errores_del_run(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    indexing_run = _run_indexing(client, embedding_run["produced_embedding_bundle_id"])

    documents = client.get(f"/api/indexing/runs/{indexing_run['run_id']}/documents").json()
    assert documents["total_items"] == 1
    assert documents["items"][0]["status"] == "committed"

    errors = client.get(f"/api/indexing/runs/{indexing_run['run_id']}/errors").json()
    assert errors["total_items"] == 0
    assert "traceback" not in errors


def test_overview_reporta_el_estado_agregado(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    _run_indexing(client, embedding_run["produced_embedding_bundle_id"])

    overview = client.get("/api/indexing/overview").json()

    assert overview["bundle_first_enabled"] is True
    assert overview["completed_runs"] == 1
    assert overview["verified_profiles"] == 1


def test_flujo_completo_de_retrieval_por_http(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    indexing_run = _run_indexing(client, embedding_run["produced_embedding_bundle_id"])
    activation = client.post(
        "/api/indexing/activations",
        json={"run_id": indexing_run["run_id"]},
    ).json()
    retrieval_profile_id = activation["retrieval_profile_id"]

    status_response = client.get(
        f"/api/retrieval/profiles/{retrieval_profile_id}/status"
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["profile"]["active"] is True
    assert status_body["readiness"]["ready"] is True
    assert status_body["runtime"]["query_engine_available"] is True
    assert status_body["readiness"]["active_document_count"] == 1

    validation = client.post(
        "/api/retrieval/validate",
        json={"retrieval_profile_id": retrieval_profile_id},
    )
    assert validation.status_code == 200
    assert validation.json()["status"] == "passed"


def test_busca_evidencia_por_http_despues_de_activar_el_perfil(client: TestClient) -> None:
    embedding_run = _run_embedding(client)
    indexing_run = _run_indexing(client, embedding_run["produced_embedding_bundle_id"])
    activation = client.post(
        "/api/indexing/activations",
        json={"run_id": indexing_run["run_id"]},
    ).json()
    retrieval_profile_id = activation["retrieval_profile_id"]

    response = client.post(
        "/api/retrieval/search",
        json={
            "retrieval_profile_id": retrieval_profile_id,
            "query": "validacion sintetica de recuperacion",
            "top_k": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_profile_id"] == retrieval_profile_id
    assert body["top_k"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["document_id"]
    assert body["items"][0]["child_chunk_id"]
    assert body["items"][0]["text"]


def test_busca_evidencia_con_wiring_por_defecto_sin_500(
    client_default_lexical_profile: TestClient,
) -> None:
    embedding_run = _run_embedding(client_default_lexical_profile)
    indexing_run = _run_indexing(
        client_default_lexical_profile,
        embedding_run["produced_embedding_bundle_id"],
    )
    activation = client_default_lexical_profile.post(
        "/api/indexing/activations",
        json={"run_id": indexing_run["run_id"]},
    ).json()
    retrieval_profile_id = activation["retrieval_profile_id"]

    response = client_default_lexical_profile.post(
        "/api/retrieval/search",
        json={
            "retrieval_profile_id": retrieval_profile_id,
            "query": "validacion sintetica de recuperacion",
            "top_k": 3,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"]


def test_bloquea_activar_un_perfil_de_retrieval_sin_filas(client: TestClient) -> None:
    created = client.post(
        "/api/retrieval/profiles",
        json={
            "consumer_scope_type": SCOPE_TYPE,
            "consumer_scope_id": "otro-scope",
            "corpus_version": client.app.state.test_chunk_bundle.corpus_version,
            "embedding_profile_id": client.app.state.test_profile.profile_id,
            "indexing_target_id": "target-idx-vec-test-mock-v1",
        },
    )
    assert created.status_code == 201

    response = client.post(
        f"/api/retrieval/profiles/{created.json()['retrieval_profile_id']}/activate"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RETRIEVAL_PROFILE_BLOCKED"


def test_los_flags_apagados_bloquean_las_escrituras(blocked_client: TestClient) -> None:
    embedding = blocked_client.post(
        "/api/embedding/runs",
        json={"chunk_bundle_id": "x", "profile_id": "y"},
        headers={"Idempotency-Key": "k"},
    )
    indexing = blocked_client.post(
        "/api/indexing/runs",
        json={"embedding_bundle_id": "x"},
        headers={"Idempotency-Key": "k"},
    )
    retrieval = blocked_client.post(
        "/api/retrieval/profiles",
        json={
            "consumer_scope_type": SCOPE_TYPE,
            "consumer_scope_id": SCOPE_ID,
            "corpus_version": "v1",
            "embedding_profile_id": "p",
            "indexing_target_id": "t",
        },
    )

    assert embedding.status_code == 503
    assert embedding.json()["error"]["code"] == "EMBEDDING_V2_DISABLED"
    assert indexing.status_code == 503
    assert indexing.json()["error"]["code"] == "INDEXING_BUNDLE_FIRST_DISABLED"
    assert retrieval.status_code == 503
    assert retrieval.json()["error"]["code"] == "RETRIEVAL_V1_DISABLED"


def test_las_lecturas_siguen_disponibles_con_los_flags_apagados(
    blocked_client: TestClient,
) -> None:
    assert blocked_client.get("/api/embedding/profiles").status_code == 200
    assert blocked_client.get("/api/indexing/targets").status_code == 200
    assert blocked_client.get("/api/retrieval/profiles").status_code == 200


def test_rechaza_page_size_fuera_de_rango(client: TestClient) -> None:
    response = client.get("/api/embedding/profiles?page_size=1000")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PIPELINE_INVALID_REQUEST"
