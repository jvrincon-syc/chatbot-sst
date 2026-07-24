from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from chunking.api.app import create_app
from ingestion.paths import ArtifactPaths


SOURCE_HASH = "c" * 64


def _sandbox(name: str) -> tuple[Path, Path]:
    root = Path("manual-test-temp") / "chunking-api" / name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    docs = root / "docs_normalized"
    chunks = root / "chunks"
    docs.mkdir(parents=True, exist_ok=True)
    chunks.mkdir(parents=True, exist_ok=True)
    return docs, chunks


def _confidence() -> dict[str, object]:
    return {
        "kind": "unavailable",
        "value": None,
        "unit": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "sample_size": None,
        "provenance": None,
        "warnings": [],
    }


def _observation() -> dict[str, object]:
    return {
        "status": "not_evaluated",
        "value": None,
        "method": None,
        "engine": None,
        "engine_version": None,
        "evidence": [],
        "warnings": [],
    }


def _document_field() -> dict[str, object]:
    return {
        "value": None,
        "value_raw": None,
        "status": "not_found",
        "evidence": [],
        "warnings": [],
    }


def _write_document(
    docs_root: Path,
    *,
    document_id: str,
    source_relpath: str,
    document_name: str,
    markdown_body: str,
) -> None:
    artifact_paths = ArtifactPaths.for_source(source_relpath)
    markdown_path = docs_root / artifact_paths.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = (
        "---\n"
        f"document_id: {document_id}\n"
        f"source_relpath: {source_relpath}\n"
        f"source_hash: {SOURCE_HASH}\n"
        "---\n"
        "<!-- page: 1 -->\n\n"
        f"{markdown_body}\n"
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    metadata = {
        "schema_version": "2.0",
        "document_id": document_id,
        "document_name": document_name,
        "source_relpath": source_relpath,
        "normalized_relpath": artifact_paths.markdown,
        "document_control": {
            "title": _document_field(),
            "code": _document_field(),
            "version": _document_field(),
            "publication_date": _document_field(),
            "effective_date": _document_field(),
        },
        "classification": {
            "document_type": "procedimiento",
            "document_type_confidence": _confidence(),
            "topic": "SST",
            "topic_confidence": _confidence(),
        },
        "page_count": 1,
        "extraction_method": "markdown",
        "ocr_confidence": _confidence(),
        "handwriting": _observation(),
        "tables": _observation(),
        "forms": _observation(),
        "source_hash": SOURCE_HASH,
        "corpus_version": "phase1",
        "pipeline_version": "2.0.0",
        "processing_status": "processed",
    }
    pages = {
        "schema_version": "2.0",
        "document_id": document_id,
        "page_count": 1,
        "pages": [
            {
                "page_number": 1,
                "text_raw": markdown_body,
                "text_normalized": markdown_body,
                "extraction_method": "markdown",
                "blocks": [],
                "ocr_confidence": _confidence(),
            }
        ],
    }
    markdown_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    markdown_path.with_suffix(".pages.json").write_text(
        json.dumps(pages), encoding="utf-8"
    )


def _write_inventory(docs_root: Path, records: list[dict[str, object]]) -> None:
    manifests = docs_root / "_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "inventory.json").write_text(
        json.dumps({"records": records}), encoding="utf-8"
    )


def _client(name: str) -> TestClient:
    docs_root, chunks_root = _sandbox(name)
    long_body = " ".join(["Frase de seguridad con evidencia y contexto." for _ in range(120)])
    _write_document(
        docs_root,
        document_id="doc_api_1",
        source_relpath="manual/doc1.pdf",
        document_name="Documento 1",
        markdown_body=long_body,
    )
    _write_document(
        docs_root,
        document_id="doc_api_2",
        source_relpath="manual/doc2.pdf",
        document_name="Documento 2",
        markdown_body="Contenido corto de apoyo.",
    )
    _write_inventory(
        docs_root,
        [
            {
                "document_id": "doc_api_1",
                "source_relpath": "manual/doc1.pdf",
                "processing_status": "processed",
                "source_hash": SOURCE_HASH,
                "document_name": "Documento 1",
            },
            {
                "document_id": "doc_api_2",
                "source_relpath": "manual/doc2.pdf",
                "processing_status": "processed",
                "source_hash": SOURCE_HASH,
                "document_name": "Documento 2",
            },
        ],
    )
    return TestClient(create_app(docs_normalized=docs_root, chunks_root=chunks_root))


def _wait_for_run_completion(client: TestClient, run_id: str) -> None:
    for _ in range(20):
        response = client.get(f"/api/chunking/runs/{run_id}")
        payload = response.json()
        if payload["status"] in {"completed", "completed_with_warnings"}:
            return
        if payload["status"] == "failed":
            raise AssertionError(f"run {run_id} failed: {payload['warnings']}")
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} did not complete in time")


def test_post_runs_devuelve_202_cuando_request_es_valido() -> None:
    client = _client("post-202")

    response = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-202"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] in {"queued", "running", "completed"}
    assert payload["requested_documents"] == 1
    assert payload["links"]["self"].endswith(payload["run_id"])


def test_post_runs_reutiliza_resultado_cuando_idempotency_key_coincide() -> None:
    client = _client("idempotent-same")

    first = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-same"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )
    second = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-same"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["run_id"] == first.json()["run_id"]


def test_post_runs_devuelve_409_cuando_key_representa_otro_payload() -> None:
    client = _client("idempotent-conflict")
    client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-conflict"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    response = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-conflict"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_2"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHUNKING_IDEMPOTENCY_CONFLICT"


def test_post_runs_rechaza_document_id_desconocido() -> None:
    client = _client("unknown-doc")

    response = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-unknown"},
        json={
            "scope": "documents",
            "document_ids": ["doc_missing"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHUNKING_DOCUMENT_NOT_FOUND"


def test_post_runs_devuelve_422_con_scope_invalido() -> None:
    client = _client("invalid-scope")

    response = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-invalid-scope"},
        json={
            "scope": "algo-invalido",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "CHUNKING_INVALID_REQUEST"
    assert "issues" in payload["error"]["details"]


def test_post_runs_devuelve_422_cuando_falta_idempotency_key() -> None:
    client = _client("missing-idempotency")

    response = client.post(
        "/api/chunking/runs",
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CHUNKING_INVALID_REQUEST"


def test_get_run_devuelve_progreso_y_enlaces() -> None:
    client = _client("get-run")
    created = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-get-run"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    ).json()
    _wait_for_run_completion(client, created["run_id"])

    response = client.get(f"/api/chunking/runs/{created['run_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completed_documents"] == 1
    assert payload["links"]["documents"].endswith("/documents")
    assert payload["links"]["validation"].endswith("/validation")


def test_get_documents_aplica_paginacion() -> None:
    client = _client("pagination")
    created = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-pagination"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1", "doc_api_2"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    ).json()
    _wait_for_run_completion(client, created["run_id"])

    response = client.get(f"/api/chunking/runs/{created['run_id']}/documents?page=1&page_size=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total_items"] == 2
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 1


def test_get_parents_no_expone_ruta_absoluta() -> None:
    client = _client("parents")
    created = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-parents"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    ).json()
    _wait_for_run_completion(client, created["run_id"])

    response = client.get("/api/chunking/documents/doc_api_1/parents")

    assert response.status_code == 200
    assert response.json()
    assert "C:\\" not in json.dumps(response.json())


def test_get_children_conserva_orden_y_overlap() -> None:
    client = _client("children")
    created = client.post(
        "/api/chunking/runs",
        headers={"Idempotency-Key": "key-children"},
        json={
            "scope": "documents",
            "document_ids": ["doc_api_1"],
            "profile_id": "local-structural-v1",
            "force": False,
        },
    ).json()
    _wait_for_run_completion(client, created["run_id"])
    parents = client.get("/api/chunking/documents/doc_api_1/parents").json()
    parent_id = parents[0]["chunk_id"]

    response = client.get(f"/api/chunking/parents/{parent_id}/children")

    assert response.status_code == 200
    children = response.json()
    assert len(children) > 1
    assert [child["ordinal"] for child in children] == sorted(child["ordinal"] for child in children)
    assert children[0]["overlap_previous_tokens"] == 0
    assert children[1]["overlap_previous_tokens"] > 0


def test_openapi_publica_contrato_de_chunking() -> None:
    client = _client("openapi")

    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert "/api/chunking/profiles" in payload["paths"]
    assert "/api/chunking/runs" in payload["paths"]
    assert "/api/chunking/runs/{run_id}" in payload["paths"]
    assert "/api/chunking/documents/{document_id}/parents" in payload["paths"]
    assert "ChunkingRunStatusSchema" in payload["components"]["schemas"]
    assert "ParentChunkSchema" in payload["components"]["schemas"]


def test_ruta_desconocida_devuelve_error_uniforme() -> None:
    client = _client("unknown-route")

    response = client.get("/api/chunking/no-existe")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "CHUNKING_ROUTE_NOT_FOUND"
