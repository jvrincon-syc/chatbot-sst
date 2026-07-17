import json
from pathlib import Path

from ingestion.validation.normalized import validate_normalized_tree


def _metadata_payload(
    normalized: Path,
    *,
    document_id: str = "doc_1",
    document_name: str = "manual.md",
    source_path: str = "data/docs_raw/manual.md",
    normalized_name: str = "manual.md",
    page_count: int = 1,
    content_hash: str = "abc",
    processing_status: str = "processed",
    extraction_method: str = "markdown",
) -> dict:
    return {
        "schema_version": "1.0",
        "document_id": document_id,
        "document_name": document_name,
        "source_path": source_path,
        "normalized_path": str(normalized / normalized_name),
        "document_type": "manual",
        "topic": "SST",
        "subtopic": None,
        "version": None,
        "publication_date": None,
        "effective_date": None,
        "page_count": page_count,
        "language": "es",
        "extraction_method": extraction_method,
        "ocr_engine": "tesseract" if extraction_method == "ocr" else None,
        "ocr_confidence": 0.9 if extraction_method == "ocr" else None,
        "contains_handwriting": False,
        "contains_tables": False,
        "content_hash": content_hash,
        "corpus_version": "test",
        "pipeline_version": "1.0.0",
        "processing_status": processing_status,
        "warnings": [],
        "processed_at": "2026-07-16T00:00:00-05:00",
    }


def _write_processed_markdown(normalized: Path, *, document_id: str = "doc_1", **overrides: object) -> dict:
    normalized.mkdir(parents=True, exist_ok=True)
    (normalized / "manual.md").write_text(
        f"---\ndocument_id: {document_id}\n---\n# Manual\n",
        encoding="utf-8",
    )
    payload = _metadata_payload(normalized, document_id=document_id, **overrides)
    (normalized / "manual.metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_validation_detects_orphan_auxiliary_files(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    normalized.mkdir(parents=True)
    (normalized / "orphan.pages.json").write_text(
        json.dumps({"schema_version": "1.0", "document_id": "doc_orphan", "page_count": 0, "pages": []}),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "orphan_files" and check.status == "failed" for check in report.checks)


def test_validation_accepts_processed_markdown_with_metadata(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    _write_processed_markdown(normalized)

    report = validate_normalized_tree(normalized)

    assert report.status == "passed"


def test_validation_detects_auxiliary_document_id_mismatch(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    _write_processed_markdown(normalized, document_id="doc_1")
    (normalized / "manual.pages.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_id": "doc_2",
                "page_count": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "text_raw": "Manual",
                        "text_normalized": "Manual",
                        "extraction_method": "markdown",
                        "ocr_confidence": None,
                        "has_handwriting_warning": False,
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "auxiliary_document_ids" and check.status == "failed" for check in report.checks)


def test_validation_detects_page_count_mismatch(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    _write_processed_markdown(normalized, page_count=2)
    (normalized / "manual.pages.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_id": "doc_1",
                "page_count": 1,
                "pages": [
                    {
                        "page_number": 1,
                        "text_raw": "Manual",
                        "text_normalized": "Manual",
                        "extraction_method": "markdown",
                        "ocr_confidence": None,
                        "has_handwriting_warning": False,
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "page_count_consistency" and check.status == "failed" for check in report.checks)


def test_validation_detects_source_hash_mismatch_from_inventory(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    source = docs_raw / "manual.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Manual\n", encoding="utf-8")
    normalized = tmp_path / "data" / "docs_normalized"
    _write_processed_markdown(normalized, source_path=str(source), content_hash="wrong")
    manifests = normalized / "_manifests"
    manifests.mkdir()
    (manifests / "inventory.json").write_text(
        json.dumps(
            [
                {
                    "document_id": "doc_1",
                    "source_path": str(source),
                    "document_name": "manual.md",
                    "detected_extension": ".md",
                    "reported_extension": ".md",
                    "mime_type": "text/markdown",
                    "content_hash": "wrong",
                    "file_size": source.stat().st_size,
                    "ingestion_date": "2026-07-16T00:00:00-05:00",
                    "category_inferred": "root",
                    "document_version": None,
                    "page_count": None,
                    "processing_status": "processed",
                    "pipeline_version": "1.0.0",
                    "corpus_version": "test",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "inventory_source_hashes" and check.status == "failed" for check in report.checks)


def test_validation_requires_review_and_failed_documents_in_manifests(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    normalized.mkdir(parents=True)
    (normalized / "review.metadata.json").write_text(
        json.dumps(
            _metadata_payload(
                normalized,
                document_id="doc_review",
                document_name="review.md",
                normalized_name="review.md",
                processing_status="needs_review",
            )
        ),
        encoding="utf-8",
    )
    (normalized / "failed.metadata.json").write_text(
        json.dumps(
            _metadata_payload(
                normalized,
                document_id="doc_failed",
                document_name="failed.md",
                normalized_name="failed.md",
                processing_status="failed",
            )
        ),
        encoding="utf-8",
    )
    manifests = normalized / "_manifests"
    manifests.mkdir()
    empty_manifest = json.dumps({"schema_version": "1.0", "documents": []})
    (manifests / "needs_review.json").write_text(empty_manifest, encoding="utf-8")
    (manifests / "errors.json").write_text(empty_manifest, encoding="utf-8")

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "status_manifests" and check.status == "failed" for check in report.checks)


def test_validation_detects_pending_inventory_records(tmp_path: Path) -> None:
    normalized = tmp_path / "data" / "docs_normalized"
    normalized.mkdir(parents=True)
    manifests = normalized / "_manifests"
    manifests.mkdir()
    (manifests / "inventory.json").write_text(
        json.dumps(
            [
                {
                    "document_id": "doc_pending",
                    "source_path": str(tmp_path / "missing.md"),
                    "document_name": "missing.md",
                    "detected_extension": ".md",
                    "reported_extension": ".md",
                    "mime_type": "text/markdown",
                    "content_hash": "abc",
                    "file_size": 0,
                    "ingestion_date": "2026-07-16T00:00:00-05:00",
                    "category_inferred": "root",
                    "document_version": None,
                    "page_count": None,
                    "processing_status": "pending",
                    "pipeline_version": "1.0.0",
                    "corpus_version": "test",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "inventory_final_statuses" and check.status == "failed" for check in report.checks)
