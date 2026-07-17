import json
from pathlib import Path

from ingestion.pipeline import run_pipeline


def test_pipeline_processes_markdown_and_tracks_pdf_needing_review(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "docs_normalized"
    (docs_raw / "copasst").mkdir(parents=True)
    (docs_raw / "copasst" / "manual.md").write_text("# Manual COPASST\n\nContenido", encoding="utf-8")
    (docs_raw / "copasst" / "scan.pdf").write_bytes(b"%PDF-1.4 fake")

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="run_test",
    )

    assert summary["processed"] == 1
    assert summary["needs_review"] == 1
    assert (normalized / "copasst" / "manual.md").exists()
    assert (normalized / "copasst" / "manual.metadata.json").exists()
    assert (normalized / "copasst" / "manual.pages.json").exists()

    needs_review = json.loads((normalized / "_manifests" / "needs_review.json").read_text(encoding="utf-8"))
    assert needs_review["items"][0]["source_relpath"].endswith("scan.pdf")
    assert set(needs_review["items"][0]["reasons"]) & {
        "pdf_extractor_unconfigured",
        "ocrmypdf_unavailable",
        "ocrmypdf_processing_failed",
        "tesseract_unavailable",
        "tesseract_language_missing",
    }

    validation = json.loads((normalized / "_manifests" / "validation_run_test.json").read_text(encoding="utf-8"))
    assert validation["status"] == "passed"


def test_pipeline_skips_unchanged_documents_on_second_run(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "docs_normalized"
    docs_raw.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n\nContenido", encoding="utf-8")

    first = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="first",
    )
    second = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="second",
    )
    third = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="third",
    )

    assert first == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert second == {"processed": 0, "failed": 0, "needs_review": 0, "skipped": 1}
    assert third == {"processed": 0, "failed": 0, "needs_review": 0, "skipped": 1}

    second_manifest = json.loads((normalized / "_manifests" / "second.json").read_text(encoding="utf-8"))
    assert second_manifest["documents"][0]["document_id"]
    assert second_manifest["documents"][0]["document_status"] == "processed"
    assert second_manifest["documents"][0]["disposition"] == "reused"


def test_pipeline_reprocesses_modified_documents_by_hash(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "docs_normalized"
    docs_raw.mkdir(parents=True)
    source = docs_raw / "manual.md"
    source.write_text("# Manual\n\nContenido inicial", encoding="utf-8")

    run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="initial",
    )
    source.write_text("# Manual\n\nContenido modificado", encoding="utf-8")

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="modified",
    )

    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    normalized_text = (normalized / "manual.md").read_text(encoding="utf-8")
    assert "Contenido modificado" in normalized_text


def test_pipeline_writes_candidate_tree_without_touching_live_root(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    live = tmp_path / "data" / "docs_normalized"
    staging = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    live.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n\nContenido", encoding="utf-8")
    (live / "live.md").write_text("live", encoding="utf-8")

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=live,
        staging_root=staging,
        only_sources=["manual.md"],
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="candidate",
    )

    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert (staging / "manual.md").exists()
    assert (live / "live.md").read_text(encoding="utf-8") == "live"
    assert not (live / "manual.md").exists()
