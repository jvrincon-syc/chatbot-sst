from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ingestion.gui.chunking_adapter import ChunkingApiBridge
from ingestion.paths import ArtifactPaths


SOURCE_HASH = "c" * 64


def _sandbox(tmp_path: Path, name: str) -> tuple[Path, Path]:
    root = tmp_path / "chunking-gui" / name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    docs_root = root / "docs_normalized"
    chunks_root = root / "chunks"
    docs_root.mkdir(parents=True, exist_ok=True)
    chunks_root.mkdir(parents=True, exist_ok=True)
    return docs_root, chunks_root


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
        json.dumps(metadata),
        encoding="utf-8",
    )
    markdown_path.with_suffix(".pages.json").write_text(
        json.dumps(pages),
        encoding="utf-8",
    )


def _write_inventory(docs_root: Path, records: list[dict[str, object]]) -> None:
    manifests = docs_root / "_manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "inventory.json").write_text(
        json.dumps({"records": records}),
        encoding="utf-8",
    )


def _wait_for_completion(api: ChunkingApiBridge, run_id: str) -> dict[str, object]:
    for _ in range(50):
        status, payload = api.handle_get(f"/api/chunking/runs/{run_id}")
        assert status == 200
        if payload["status"] in {"completed", "completed_with_warnings"}:
            return payload
        if payload["status"] == "failed":
            raise AssertionError(f"run {run_id} failed: {payload['warnings']}")
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not complete in time")


def test_gui_chunking_bridge_serves_profiles_and_run_inspection(tmp_path: Path) -> None:
    docs_root, chunks_root = _sandbox(tmp_path, "happy-path")
    long_body = " ".join(["Frase de seguridad con evidencia y contexto." for _ in range(120)])
    _write_document(
        docs_root,
        document_id="doc_gui_1",
        source_relpath="manual/doc1.pdf",
        document_name="Documento GUI 1",
        markdown_body=long_body,
    )
    _write_inventory(
        docs_root,
        [
            {
                "document_id": "doc_gui_1",
                "source_relpath": "manual/doc1.pdf",
                "processing_status": "processed",
                "source_hash": SOURCE_HASH,
                "document_name": "Documento GUI 1",
            }
        ],
    )

    api = ChunkingApiBridge(docs_normalized=docs_root, chunks_root=chunks_root)
    try:
        status, profiles = api.handle_get("/api/chunking/profiles")
        assert status == 200
        assert profiles[0]["profile_id"] == "local-structural-v1"

        status, created = api.handle_post(
            "/api/chunking/runs",
            {
                "scope": "documents",
                "document_ids": ["doc_gui_1"],
                "profile_id": "local-structural-v1",
                "force": False,
            },
            {"Idempotency-Key": "gui-chunking-key"},
        )

        assert status == 202
        run_id = created["run_id"]
        _wait_for_completion(api, run_id)

        status, documents = api.handle_get(f"/api/chunking/runs/{run_id}/documents?page=1&page_size=1")
        assert status == 200
        assert documents["total_items"] == 1
        assert documents["items"][0]["document_id"] == "doc_gui_1"

        status, parents = api.handle_get(f"/api/chunking/documents/doc_gui_1/parents?run_id={run_id}")
        assert status == 200
        assert parents["items"]
    finally:
        api.close()


def test_gui_chunking_bridge_rejects_unknown_route(tmp_path: Path) -> None:
    docs_root, chunks_root = _sandbox(tmp_path, "unknown-route")
    _write_inventory(docs_root, [])

    api = ChunkingApiBridge(docs_normalized=docs_root, chunks_root=chunks_root)
    try:
        status, payload = api.handle_get("/api/chunking/no-existe")
        assert status == 404
        assert payload["error"]["code"] == "CHUNKING_ROUTE_NOT_FOUND"
    finally:
        api.close()
