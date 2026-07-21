import json
from pathlib import Path

import pytest

import ingestion.pipeline as pipeline_module
from ingestion.pipeline import _configured_tesseract_engine, run_pipeline
from ingestion.promotion import PromotionError
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import FormsArtifact, PageRecord, TablesArtifact
from ingestion.schemas.common import ConfidenceMetric, Observation


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


def test_pipeline_writes_complete_schema2_bundle_without_inventing_capabilities(
    tmp_path: Path,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "manual.md").write_text(
        "# Manual\n\nContenido",
        encoding="utf-8",
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="schema2_bundle",
    )

    assert summary == {
        "processed": 1,
        "failed": 0,
        "needs_review": 0,
        "skipped": 0,
    }
    for suffix in (
        ".md",
        ".metadata.json",
        ".pages.json",
        ".ocr.json",
        ".tables.json",
        ".forms.json",
    ):
        assert (candidate / f"manual{suffix}").exists()

    metadata = json.loads(
        (candidate / "manual.metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["handwriting"]["status"] == "not_evaluated"
    assert metadata["tables"]["status"] == "not_evaluated"
    assert metadata["forms"]["status"] == "not_evaluated"

    run = json.loads(
        (candidate / "_manifests" / "schema2_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(run["bundles"]) == 1
    assert len(run["bundles"][0]["artifact_hashes"]) == 6


def test_pipeline_propagates_material_page_warnings_to_document_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n", encoding="utf-8")
    result = ReadResult(
        extraction_method="markdown",
        markdown="# Manual",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="# Manual",
                text_normalized="# Manual",
                extraction_method="markdown",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
                warnings=["incomplete_coverage"],
            )
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "_read_document",
        lambda *_args, **_kwargs: result,
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="warning_propagation",
    )

    assert summary["needs_review"] == 1
    metadata = json.loads(
        (candidate / "manual.metadata.json").read_text(encoding="utf-8")
    )
    assert "incomplete_coverage" in metadata["warnings"]
    assert "incomplete_coverage" in metadata["review_reasons"]
    assert metadata["processing_status"] == "needs_review"


def test_pipeline_marks_pdf_with_unevaluated_material_features_as_needs_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "documento.pdf").write_bytes(b"%PDF-1.4 fake")
    result = ReadResult(
        extraction_method="pdf_digital",
        markdown="Texto PDF",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Texto PDF",
                text_normalized="Texto PDF",
                extraction_method="pdf_digital",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "_read_document",
        lambda *_args, **_kwargs: result,
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="pdf_unevaluated_features",
    )

    assert summary["needs_review"] == 1
    metadata = json.loads(
        (candidate / "documento.metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["processing_status"] == "needs_review"
    assert "handwriting_not_evaluated" in metadata["review_reasons"]


def test_pipeline_keeps_pdf_under_semantic_review_after_feature_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "documento.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="pdf_digital",
        markdown="Documento PDF",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Documento PDF",
                text_normalized="Documento PDF",
                extraction_method="pdf_digital",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[
                Observation(status="not_detected", value=False, method="test")
            ],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[
                Observation(status="not_detected", value=False, method="test")
            ],
        ),
    )
    monkeypatch.setattr(
        pipeline_module,
        "_read_document",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(
            status="not_detected",
            value=False,
            method="test",
        ),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="pdf_semantic_review",
        classification_review_threshold=0.0,
    )

    assert summary["needs_review"] == 1
    metadata = json.loads(
        (candidate / "documento.metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["processing_status"] == "needs_review"
    assert "pdf_semantic_review_required" in metadata["review_reasons"]


def test_pipeline_normalizes_windows_only_source_paths(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "normalized"
    (docs_raw / "nested").mkdir(parents=True)
    (docs_raw / "nested" / "manual.md").write_text(
        "# Manual\n",
        encoding="utf-8",
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        only_sources=[r"nested\manual.md"],
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="windows_selection",
    )

    assert summary["processed"] == 1
    assert (normalized / "nested" / "manual.metadata.json").exists()


def test_pipeline_configures_region_tesseract_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TESSERACT_CMD", r"C:\Tools\Tesseract\tesseract.exe")
    monkeypatch.setenv("TESSERACT_LANGUAGE", "spa")
    monkeypatch.setenv("TESSERACT_VERSION", "5.4.0")

    engine = _configured_tesseract_engine()

    assert engine.tesseract_cmd == r"C:\Tools\Tesseract\tesseract.exe"
    assert engine.language == "spa"
    assert engine.engine_version == "5.4.0"


def test_pipeline_refuses_promotion_without_explicit_golden_pass(
    tmp_path: Path,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    live = tmp_path / "data" / "live"
    staging = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    live.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n\nContenido", encoding="utf-8")
    (live / "live.md").write_text("live", encoding="utf-8")

    with pytest.raises(PromotionError):
        run_pipeline(
            docs_raw=docs_raw,
            docs_normalized=live,
            staging_root=staging,
            promote=True,
            corpus_version="test",
            pipeline_version="2.0.0",
            run_id="unsafe_promote",
        )

    assert (live / "live.md").read_text(encoding="utf-8") == "live"
    assert not (live / "manual.md").exists()
