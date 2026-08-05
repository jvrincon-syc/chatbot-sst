from __future__ import annotations

import json
from pathlib import Path

import pytest

from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.application.run_service import (
    ChunkingIdempotencyConflictError,
    ChunkingRunRequest,
    ChunkingRunService,
)
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from ingestion.paths import ArtifactPaths


SOURCE_HASH = "d" * 64


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
        "document_name": source_relpath.rsplit("/", 1)[-1],
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
        "handwriting": {
            "status": "not_evaluated",
            "value": None,
            "method": None,
            "engine": None,
            "engine_version": None,
            "evidence": [],
            "warnings": [],
        },
        "tables": {
            "status": "not_evaluated",
            "value": None,
            "method": None,
            "engine": None,
            "engine_version": None,
            "evidence": [],
            "warnings": [],
        },
        "forms": {
            "status": "not_evaluated",
            "value": None,
            "method": None,
            "engine": None,
            "engine_version": None,
            "evidence": [],
            "warnings": [],
        },
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


def _service(root: Path) -> ChunkingRunService:
    docs_root = root / "docs_normalized"
    chunks_root = root / "chunks"
    chunk_repository = FilesystemChunkBundleRepository(output_root=chunks_root)
    return ChunkingRunService(
        docs_normalized=docs_root,
        chunks_root=chunks_root,
        source=Schema2NormalizedDocumentSource(docs_root),
        orchestrator=ChunkingOrchestrator(
            engine=LocalChunkingEngine(),
            bundle_repository=chunk_repository,
            run_repository=FilesystemRunRepository(output_root=chunks_root),
        ),
        chunk_repository=chunk_repository,
    )


def test_rehidrata_corrida_y_reconstruye_idempotencia(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs_normalized"
    docs_root.mkdir(parents=True, exist_ok=True)
    _write_document(
        docs_root,
        document_id="doc_reload_1",
        source_relpath="manual/reload_1.pdf",
        markdown_body=(
            "# Primera seccion\n\n"
            + " ".join(["Contenido semantico con trazabilidad." for _ in range(35)])
        ),
    )
    _write_document(
        docs_root,
        document_id="doc_reload_2",
        source_relpath="manual/reload_2.pdf",
        markdown_body=(
            "# Otra seccion\n\n"
            + " ".join(["Contenido alterno con evidencia." for _ in range(35)])
        ),
    )
    _write_inventory(
        docs_root,
        [
            {
                "document_id": "doc_reload_1",
                "source_relpath": "manual/reload_1.pdf",
                "processing_status": "processed",
                "source_hash": SOURCE_HASH,
                "document_name": "reload_1.pdf",
            },
            {
                "document_id": "doc_reload_2",
                "source_relpath": "manual/reload_2.pdf",
                "processing_status": "processed",
                "source_hash": SOURCE_HASH,
                "document_name": "reload_2.pdf",
            },
        ],
    )

    first_service = _service(tmp_path)
    request = ChunkingRunRequest(
        scope="documents",
        document_ids=("doc_reload_1",),
        profile_id="local-structural-v1",
        force=False,
    )
    created = first_service.create_run(request=request, idempotency_key="reload-key")
    assert created.status == "queued"
    first_service.close()

    reloaded_service = _service(tmp_path)
    reloaded_state = reloaded_service.get_run_state(created.run_id)
    assert reloaded_state.status == "interrupted"
    assert reloaded_state.idempotency_key == "reload-key"

    same_request = reloaded_service.create_run(
        request=request,
        idempotency_key="reload-key",
    )
    assert same_request.run_id == created.run_id
    assert same_request.status == "interrupted"

    with pytest.raises(ChunkingIdempotencyConflictError):
        reloaded_service.create_run(
            request=ChunkingRunRequest(
                scope="documents",
                document_ids=("doc_reload_2",),
                profile_id="local-structural-v1",
                force=False,
            ),
            idempotency_key="reload-key",
        )

    reloaded_service.execute_run(created.run_id)
    completed = reloaded_service.get_run_payload(created.run_id)
    assert completed["status"] == "completed"
    assert completed["completed_documents"] == 1
    reloaded_service.close()
