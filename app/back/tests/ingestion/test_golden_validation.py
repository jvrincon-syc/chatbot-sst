import json
from pathlib import Path

import pytest

from ingestion.paths import stable_document_id
from ingestion.pipeline import run_pipeline
from ingestion.validation.golden import (
    GoldenContentExpectation,
    GoldenCorpus,
    GoldenDocument,
    GoldenExpected,
    load_golden,
    validate_pdf_corpus,
)


def test_golden_loader_strips_raw_root_prefix_and_keeps_77_page_total() -> None:
    golden = load_golden(Path("docs/ingestion/pdf_corpus_expected.json"))

    assert len(golden.documents) == 9
    assert sum(document.page_count for document in golden.documents) == 77
    assert all(not document.source_relpath.startswith("data/docs_raw/") for document in golden.documents)


def test_golden_validator_requires_exact_source_bijection(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    candidate = tmp_path / "candidate"
    raw.mkdir()
    candidate.mkdir()
    (raw / "expected.pdf").write_bytes(b"%PDF")
    (candidate / "extra.metadata.json").write_text("{}", encoding="utf-8")
    golden = GoldenCorpus(
        audit_schema_version="test",
        documents=[
            GoldenDocument(
                document_id="doc_expected",
                source_relpath="expected.pdf",
                page_count=77,
                expected={},
                review_status="needs_review",
            )
        ],
    )

    report = validate_pdf_corpus(candidate, raw, golden)

    assert report.status == "failed"
    assert any(check.check == "golden_bijection" and check.status == "failed" for check in report.checks)


def test_golden_validator_allows_valid_extra_non_pdf_candidate_metadata(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    candidate = tmp_path / "candidate"
    raw.mkdir()
    (raw / "expected.md").write_text("# Esperado\n\nContenido", encoding="utf-8")
    (raw / "extra.md").write_text("# Extra\n\nContenido", encoding="utf-8")
    run_pipeline(
        docs_raw=raw,
        docs_normalized=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="golden_full_candidate_fixture",
    )
    golden = GoldenCorpus(
        audit_schema_version="test",
        documents=[
            GoldenDocument(
                document_id=stable_document_id("expected.md"),
                source_relpath="expected.md",
                page_count=1,
                expected=GoldenExpected(),
                review_status="processed",
            )
        ],
    )

    report = validate_pdf_corpus(candidate, raw, golden)

    assert any(
        check.check == "golden_bijection" and check.status == "passed"
        for check in report.checks
    )


def test_golden_validator_compares_actual_metadata_status_and_pages(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    candidate = tmp_path / "candidate"
    raw.mkdir()
    (raw / "expected.md").write_text("# Manual\n\nContenido", encoding="utf-8")
    run_pipeline(
        docs_raw=raw,
        docs_normalized=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="golden_fixture",
    )
    source_relpath = "expected.md"
    golden = GoldenCorpus(
        audit_schema_version="test",
        documents=[
            GoldenDocument(
                document_id=stable_document_id(source_relpath),
                source_relpath=source_relpath,
                page_count=2,
                expected=GoldenExpected(
                    title="Manual",
                    document_type="formulario",
                    topic="SST",
                    extraction_method="markdown",
                    contains_tables="not_evaluated",
                    contains_form="not_evaluated",
                    contains_handwriting="not_evaluated",
                ),
                review_status="needs_review",
            )
        ],
    )

    report = validate_pdf_corpus(candidate, raw, golden)

    assert report.status == "failed"
    assert any(
        check.check == "golden_metadata" and check.status == "failed"
        for check in report.checks
    )
    assert any(
        check.check == "golden_pages" and check.status == "failed"
        for check in report.checks
    )


def test_golden_validator_executes_minimum_content_expectations(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    candidate = tmp_path / "candidate"
    raw.mkdir()
    (raw / "expected.md").write_text(
        "# Manual\n\nContenido presente",
        encoding="utf-8",
    )
    run_pipeline(
        docs_raw=raw,
        docs_normalized=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="golden_content_fixture",
    )
    source_relpath = "expected.md"
    golden = GoldenCorpus(
        audit_schema_version="test",
        documents=[
            GoldenDocument(
                document_id=stable_document_id(source_relpath),
                source_relpath=source_relpath,
                page_count=1,
                expected=GoldenExpected(),
                minimum_content=[
                    GoldenContentExpectation(
                        pages="1",
                        must_preserve=["contenido ausente"],
                        structure="Preserve the heading.",
                    )
                ],
                review_status="processed",
            )
        ],
    )

    report = validate_pdf_corpus(candidate, raw, golden)

    assert any(
        check.check == "golden_content" and check.status == "failed"
        and "contenido ausente" in " ".join(check.details)
        for check in report.checks
    )


def test_golden_content_expectations_reject_descriptive_must_preserve() -> None:
    with pytest.raises(ValueError, match="literal source anchors"):
        GoldenContentExpectation(
            pages="1",
            must_preserve=["three objective rows"],
            structure="Keep narrative expectations here instead.",
        )
