import json
from pathlib import Path

from ingestion.inventory.scanner import compute_content_hash
from ingestion.pipeline import run_pipeline
from ingestion.validation.normalized import validate_normalized_tree


def _confidence(value: float = 0.95) -> dict:
    return {"kind": "estimated", "value": value, "method": "test"}


def _unavailable_confidence() -> dict:
    return {"kind": "unavailable", "value": None}


def _not_detected(method: str = "test") -> dict:
    return {"status": "not_detected", "value": False, "method": method}


def _not_evaluated() -> dict:
    return {"status": "not_evaluated", "value": None}


def _document_control() -> dict:
    extracted = {
        "value": "Manual",
        "value_raw": "Manual",
        "status": "extracted",
        "evidence": [{"page_number": 1, "text": "Manual", "source": "test"}],
    }
    empty = {"value": None, "status": "not_found", "evidence": []}
    return {
        "title": extracted,
        "code": empty,
        "version": empty,
        "publication_date": empty,
        "effective_date": empty,
        "change_history": [],
        "warnings": [],
    }


def _metadata_payload(
    *,
    document_id: str = "doc_1",
    document_name: str = "manual.md",
    source_relpath: str = "manual.md",
    normalized_relpath: str = "manual.md",
    page_count: int = 1,
    source_hash: str = "abc",
    processing_status: str = "processed",
    review_reasons: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "2.0",
        "document_id": document_id,
        "document_name": document_name,
        "source_relpath": source_relpath,
        "normalized_relpath": normalized_relpath,
        "document_control": _document_control(),
        "classification": {
            "document_type": "manual",
            "document_type_confidence": _confidence(),
            "topic": "SST",
            "topic_confidence": _confidence(),
            "signals": ["test"],
        },
        "page_count": page_count,
        "language": "es",
        "extraction_method": "markdown",
        "ocr_confidence": _unavailable_confidence(),
        "handwriting": _not_evaluated(),
        "tables": _not_detected(),
        "forms": _not_detected(),
        "source_hash": source_hash,
        "corpus_version": "test",
        "pipeline_version": "1.0.0",
        "processing_status": processing_status,
        "review_reasons": review_reasons or [],
        "warnings": [],
    }


def _pages_payload(document_id: str = "doc_1", page_numbers: list[int] | None = None) -> dict:
    page_numbers = page_numbers or [1]
    return {
        "schema_version": "2.0",
        "document_id": document_id,
        "page_count": len(page_numbers),
        "pages": [
            {
                "page_number": page_number,
                "text_raw": "Manual",
                "text_normalized": "Manual",
                "extraction_method": "markdown",
                "ocr_confidence": _unavailable_confidence(),
                "warnings": [],
            }
            for page_number in page_numbers
        ],
    }


def _write_document(normalized: Path, **metadata_overrides: object) -> dict:
    normalized.mkdir(parents=True, exist_ok=True)
    metadata = _metadata_payload(**metadata_overrides)
    (normalized / "manual.md").write_text(
        f"---\ndocument_id: {metadata['document_id']}\nsource_relpath: {metadata['source_relpath']}\n---\n# Manual\n",
        encoding="utf-8",
    )
    (normalized / "manual.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (normalized / "manual.pages.json").write_text(
        json.dumps(_pages_payload(metadata["document_id"])),
        encoding="utf-8",
    )
    return metadata


def test_validation_accepts_schema2_markdown_with_pages_and_front_matter(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_document(normalized)

    report = validate_normalized_tree(normalized)

    assert report.status == "passed"


def test_validation_detects_page_ordering_and_document_id_mismatch(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_document(normalized, document_id="doc_1")
    (normalized / "manual.pages.json").write_text(
        json.dumps(_pages_payload("doc_2", [1, 3])),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "auxiliary_document_ids" and check.status == "failed" for check in report.checks)
    assert any(check.check == "page_ordering_contiguity" and check.status == "failed" for check in report.checks)


def test_validation_checks_inventory_hashes_and_bijection_with_raw_root(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "manual.md"
    source.write_text("# Manual\n", encoding="utf-8")
    normalized = tmp_path / "normalized"
    _write_document(normalized, source_hash="wrong")
    manifests = normalized / "_manifests"
    manifests.mkdir()
    (manifests / "inventory.json").write_text(
        json.dumps(
            [
                {
                    "schema_version": "2.0",
                    "document_id": "doc_1",
                    "source_relpath": "manual.md",
                    "document_name": "manual.md",
                    "detected_extension": ".md",
                    "reported_extension": ".md",
                    "mime_type": "text/markdown",
                    "content_hash": "wrong",
                    "file_size": source.stat().st_size,
                    "ingestion_date": "2026-07-17T00:00:00-05:00",
                    "category_inferred": "root",
                    "processing_status": "processed",
                    "pipeline_version": "1.0.0",
                    "corpus_version": "test",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized, raw_root=raw)

    assert report.status == "failed"
    assert any(check.check == "inventory_source_hashes" and check.status == "failed" for check in report.checks)


def test_inventory_bijection_includes_needs_review_artifacts(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_document(
        normalized,
        processing_status="needs_review",
        review_reasons=["manual_review"],
    )
    manifests = normalized / "_manifests"
    manifests.mkdir()
    (manifests / "inventory.json").write_text(
        json.dumps(
            [
                {
                    "schema_version": "2.0",
                    "document_id": "doc_1",
                    "source_relpath": "manual.md",
                    "document_name": "manual.md",
                    "detected_extension": ".md",
                    "reported_extension": ".md",
                    "mime_type": "text/markdown",
                    "content_hash": "abc",
                    "file_size": 1,
                    "ingestion_date": "2026-07-17T00:00:00-05:00",
                    "category_inferred": "root",
                    "processing_status": "needs_review",
                    "pipeline_version": "1.0.0",
                    "corpus_version": "test",
                }
            ]
        ),
        encoding="utf-8",
    )
    (manifests / "needs_review.json").write_text(
        json.dumps({"items": [{"document_id": "doc_1"}]}),
        encoding="utf-8",
    )

    report = validate_normalized_tree(normalized)

    check = next(
        item
        for item in report.checks
        if item.check == "inventory_metadata_bijection"
    )
    assert check.status == "passed"


def test_validation_closure_rejects_legacy_and_missing_pdf_sidecars(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_document(normalized, document_name="manual.pdf", source_relpath="manual.pdf", normalized_relpath="manual.md")
    legacy = normalized / "legacy.metadata.json"
    legacy.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

    normal = validate_normalized_tree(normalized, mode="normal")
    closure = validate_normalized_tree(normalized, mode="closure")

    assert any(check.check == "metadata_schema" and check.status == "warning" for check in normal.checks)
    assert any(check.check == "metadata_schema" and check.status == "failed" for check in closure.checks)
    assert any(check.check == "closure_required_artifacts" and check.status == "failed" for check in closure.checks)


def test_validation_rejects_processed_documents_with_review_reasons(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized"
    _write_document(normalized, review_reasons=["ambiguous_classification"])

    report = validate_normalized_tree(normalized)

    assert report.status == "failed"
    assert any(check.check == "processed_with_review_reasons" and check.status == "failed" for check in report.checks)


def test_validation_stage_ignores_golden_expectations(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "manual.md").write_text("# Manual\n", encoding="utf-8")
    normalized = tmp_path / "normalized"
    _write_document(normalized)
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            {
                "audit_schema_version": "test",
                "documents": [
                    {
                        "document_id": "doc_1",
                        "source_relpath": "data/docs_raw/manual.md",
                        "page_count": 1,
                        "expected": {"title": "Titulo que no coincide"},
                        "minimum_content": [
                            {
                                "pages": "1",
                                "must_preserve": ["texto inexistente"],
                                "structure": "Only standalone golden audits check this.",
                            }
                        ],
                        "review_status": "needs_review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_normalized_tree(
        normalized,
        raw_root=raw,
        golden_path=golden,
    )

    assert report.status == "passed"
    assert report.errors == 0
    assert all(not check.check.startswith("golden_") for check in report.checks)


def test_closure_preserves_multipoint_artifact_stems(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    normalized = tmp_path / "normalized"
    raw.mkdir()
    (raw / "RE.RH-04.md").write_text("# Manual\n", encoding="utf-8")
    run_pipeline(
        docs_raw=raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="multipoint",
    )
    metadata_path = normalized / "RE.RH-04.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["document_name"] = "RE.RH-04.pdf"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    report = validate_normalized_tree(normalized, mode="closure")

    closure = next(
        check for check in report.checks
        if check.check == "closure_required_artifacts"
    )
    assert closure.status == "passed"
