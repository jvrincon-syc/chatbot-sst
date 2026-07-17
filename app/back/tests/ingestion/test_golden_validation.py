import json
from pathlib import Path

from ingestion.validation.golden import GoldenCorpus, GoldenDocument, load_golden, validate_pdf_corpus


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
