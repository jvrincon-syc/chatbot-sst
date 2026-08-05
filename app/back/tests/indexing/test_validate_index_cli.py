from __future__ import annotations

import json

from scripts.indexing.validate_index import validate_index_state


def test_validate_index_state_fails_when_approved_artifact_is_missing(tmp_path) -> None:
    root = tmp_path / "docs_normalized"
    manifests = root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": "doc_missing",
                        "source_relpath": "manual/doc.pdf",
                        "processing_status": "processed",
                        "source_hash": "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_index_state(normalized_root=root, profile="test")

    assert result["status"] == "failed"
    assert "missing_artifact:manual/doc.md" in result["errors"]


def test_validate_index_state_passes_when_approved_artifacts_exist(tmp_path) -> None:
    root = tmp_path / "docs_normalized"
    manifests = root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": "doc_ok",
                        "source_relpath": "manual/doc.pdf",
                        "processing_status": "processed",
                        "source_hash": "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for suffix in (".md", ".metadata.json", ".pages.json", ".tables.json", ".forms.json"):
        target = root / f"manual/doc{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

    result = validate_index_state(normalized_root=root, profile="test")

    assert result["status"] == "passed"
    assert result["approved_documents"] == 1


def test_validate_index_state_includes_human_approved_needs_review_documents(tmp_path) -> None:
    root = tmp_path / "docs_normalized"
    manifests = root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": "doc_processed",
                        "source_relpath": "manual/processed.pdf",
                        "processing_status": "processed",
                        "source_hash": "a" * 64,
                    },
                    {
                        "document_id": "doc_reviewed",
                        "source_relpath": "manual/reviewed.pdf",
                        "processing_status": "needs_review",
                        "source_hash": "b" * 64,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (manifests / "review_decisions.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "document_id": "doc_reviewed",
                        "source_relpath": "manual/reviewed.pdf",
                        "decision": "approved",
                        "reason": "Revision humana completada.",
                        "decided_at": "2026-07-28T10:00:00-05:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for source in ("manual/processed", "manual/reviewed"):
        for suffix in (".md", ".metadata.json", ".pages.json", ".tables.json", ".forms.json"):
            target = root / f"{source}{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")

    result = validate_index_state(normalized_root=root, profile="test")

    assert result["status"] == "passed"
    assert result["approved_documents"] == 2


def test_validate_index_reports_mixed_provider_as_error() -> None:
    report = validate_index_state(
        documents=[{"document_id": "doc_1", "ingestion_origin": "local", "approved": True}],
        profiles=[
            {
                "profile_id": "llama-bge-m3-v1",
                "ingestion_origin": "llama_cloud",
                "embedding_dimension": 1024,
            }
        ],
        vectors=[
            {
                "node_id": "child_1",
                "document_id": "doc_1",
                "profile_id": "llama-bge-m3-v1",
                "embedding_dimension": 1024,
            }
        ],
        nodes=[{"node_id": "child_1", "document_id": "doc_1", "node_role": "child"}],
    )

    assert report.status == "failed"
    assert report.mixed_provider_errors == 1


def test_validate_index_reports_dimension_mismatch_and_orphan_vectors() -> None:
    report = validate_index_state(
        documents=[
            {"document_id": "doc_1", "ingestion_origin": "llama_cloud", "approved": True}
        ],
        profiles=[
            {
                "profile_id": "llama-bge-m3-v1",
                "ingestion_origin": "llama_cloud",
                "embedding_dimension": 1024,
            }
        ],
        vectors=[
            {
                "node_id": "missing_child",
                "document_id": "doc_1",
                "profile_id": "llama-bge-m3-v1",
                "embedding_dimension": 384,
            }
        ],
        nodes=[],
    )

    assert report.status == "failed"
    assert report.dimension_errors == 1
    assert report.orphan_vectors == 1


def test_validate_index_reports_unapproved_document_vectors() -> None:
    report = validate_index_state(
        documents=[
            {"document_id": "doc_1", "ingestion_origin": "llama_cloud", "approved": False}
        ],
        profiles=[
            {
                "profile_id": "llama-bge-m3-v1",
                "ingestion_origin": "llama_cloud",
                "embedding_dimension": 1024,
            }
        ],
        vectors=[
            {
                "node_id": "child_1",
                "document_id": "doc_1",
                "profile_id": "llama-bge-m3-v1",
                "embedding_dimension": 1024,
            }
        ],
        nodes=[{"node_id": "child_1", "document_id": "doc_1", "node_role": "child"}],
    )

    assert report.status == "failed"
    assert report.unapproved_document_errors == 1
