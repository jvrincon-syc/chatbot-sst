import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import ingestion.pipeline as pipeline_module
from ingestion.config.llama_settings import LlamaSettings
from ingestion.domain.models.classification import (
    ClassificationCandidate,
    ClassificationResult,
)
from ingestion.domain.models.extraction import ExtractionField, ExtractionResult
from ingestion.domain.models.llama_understanding import LlamaUnderstanding
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.pipeline import _configured_tesseract_engine, _run_pipeline_legacy, run_pipeline
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import (
    FormsArtifact,
    LlamaCloudMetadata,
    OcrArtifact,
    PageRecord,
    TablesArtifact,
)
from ingestion.schemas.common import ConfidenceMetric, Evidence, Observation


@pytest.fixture(autouse=True)
def _disable_llama_cloud_for_local_pipeline_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_CLOUD_ENABLED", "false")
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)


def _llama_job(capability: str, job_id: str) -> ProviderJobRef:
    now = datetime.now(timezone.utc)
    return ProviderJobRef(
        provider="llama_cloud",
        capability=capability,
        job_id=job_id,
        status="completed",
        configuration_hash="sha256:test",
        created_at=now,
        completed_at=now,
    )


def _llama_classification(capability: str, label: str, confidence: float = 0.96) -> ClassificationResult:
    return ClassificationResult(
        provider_job=_llama_job("classify", f"{capability}_job"),
        selected=ClassificationCandidate(
            label=label,
            confidence=confidence,
            evidence=[Evidence(page_number=1, text=label, source="llama_classify")],
            reasoning_summary="Clasificacion basada en contenido del documento.",
        ),
    )


def _ocr_artifact(confidence: float) -> OcrArtifact:
    return OcrArtifact(
        schema_version="2.0",
        document_id="pending",
        document_confidence=ConfidenceMetric(
            kind="estimated",
            value=confidence,
            method="test_provider_ocr_confidence",
        ),
        pages=[],
    )


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


def test_legacy_pipeline_helper_delegates_to_current_run_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    docs_normalized = tmp_path / "data" / "docs_normalized"
    docs_raw.mkdir(parents=True)
    docs_normalized.mkdir(parents=True)
    captured: dict[str, object] = {}

    def fake_run_pipeline(**kwargs: object) -> dict[str, int]:
        captured.update(kwargs)
        return {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}

    monkeypatch.setattr(pipeline_module, "run_pipeline", fake_run_pipeline)

    summary = _run_pipeline_legacy(
        docs_raw=docs_raw,
        docs_normalized=docs_normalized,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="legacy-alias",
    )

    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert captured["docs_raw"] == docs_raw
    assert captured["docs_normalized"] == docs_normalized
    assert captured["corpus_version"] == "test"
    assert captured["pipeline_version"] == "2.0.0"
    assert captured["run_id"] == "legacy-alias"


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


def test_pipeline_does_not_keep_pdf_under_semantic_review_after_feature_evaluation(
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

    assert summary["processed"] == 1
    metadata = json.loads(
        (candidate / "documento.metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["processing_status"] == "processed"
    assert "pdf_semantic_review_required" not in metadata["review_reasons"]


def test_pipeline_processes_pdf_when_material_features_are_evaluated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "politica.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="llamaparse",
        markdown="# Politica SST\n\nContenido.",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="# Politica SST\n\nContenido.",
                text_normalized="Politica SST\n\nContenido.",
                extraction_method="llamaparse",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_markdown_table")],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_form_heuristic")],
        ),
        ocr=_ocr_artifact(0.93),
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="pdf_features_evaluated",
        classification_review_threshold=0.0,
    )

    metadata = json.loads((candidate / "politica.metadata.json").read_text(encoding="utf-8"))
    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert metadata["processing_status"] == "processed"
    assert "pdf_semantic_review_required" not in metadata["review_reasons"]


def test_pipeline_uses_llama_classify_without_penalizing_arbitrary_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    source_dir = docs_raw / "convivencia_laboral" / "manual"
    source_dir.mkdir(parents=True)
    (source_dir / "registro.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="llamaparse",
        markdown="# Formulario de queja por convivencia laboral\n\nCodigo CV-F-01",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Formulario de queja por convivencia laboral Codigo CV-F-01",
                text_normalized="Formulario de queja por convivencia laboral Codigo CV-F-01",
                extraction_method="llamaparse",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_markdown_table")],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_form_heuristic")],
        ),
        ocr=_ocr_artifact(0.94),
        llama_understanding=LlamaUnderstanding(
            parse_job_id="pjb_classified",
            document_type=_llama_classification("document_type", "formulario"),
            topic=_llama_classification("topic", "convivencia_laboral"),
            schema_extract="formulario_document_control",
        ),
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_classify_metadata",
        classification_review_threshold=0.0,
    )

    metadata = json.loads(
        (candidate / "convivencia_laboral" / "manual" / "registro.metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert metadata["classification"]["document_type"] == "formulario"
    assert metadata["classification"]["topic"] == "Convivencia laboral"
    assert metadata["classification"]["conflict_status"] == "none"
    assert "classification_conflict" not in metadata["review_reasons"]
    assert "llama_classify_document_type:formulario" in metadata["classification"]["signals"]
    assert "llama_schema_extract:formulario_document_control" in metadata["classification"]["signals"]


def test_pipeline_marks_unsupported_llama_extract_critical_fields_for_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "politica.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="llamaparse",
        markdown="# Politica SST\n\nCodigo SST-PO-01",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Politica SST Codigo SST-PO-01",
                text_normalized="Politica SST Codigo SST-PO-01",
                extraction_method="llamaparse",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_markdown_table")],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[Observation(status="not_detected", value=False, method="llamaparse_form_heuristic")],
        ),
        llama_understanding=LlamaUnderstanding(
            parse_job_id="pjb_extract",
            document_type=_llama_classification("document_type", "politica"),
            topic=_llama_classification("topic", "sg_sst"),
            extraction=ExtractionResult(
                provider_job=_llama_job("extract", "extract_unsupported"),
                schema_name="politica_document_control",
                fields=[
                    ExtractionField(
                        name="code",
                        value="NO-SOPORTADO",
                        critical=True,
                        evidence=[Evidence(page_number=1, text="NO-SOPORTADO", source="llama_extract")],
                    )
                ],
            ),
            warnings=["llama_extract_unsupported_critical_field:code"],
        ),
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_extract_review",
        classification_review_threshold=0.0,
    )

    metadata = json.loads((candidate / "politica.metadata.json").read_text(encoding="utf-8"))
    assert summary["needs_review"] == 1
    assert metadata["processing_status"] == "needs_review"
    assert "llama_extract_unsupported_critical_field:code" in metadata["review_reasons"]
    assert "llama_extract_unsupported_critical_field:code" in metadata["warnings"]


def test_pipeline_records_ocr_confidence_in_inventory_and_reviews_below_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "scan.pdf").write_bytes(b"%PDF-1.4 fake")

    measured_confidence = ConfidenceMetric(
        kind="measured",
        value=0.79,
        engine="tesseract",
        engine_version="5.4.0",
        unit="mean_word_confidence",
        sample_size=42,
    )
    result = ReadResult(
        extraction_method="ocr",
        markdown="Texto OCR",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="Texto OCR",
                text_normalized="Texto OCR",
                extraction_method="ocr",
                ocr_confidence=measured_confidence,
            )
        ],
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="ocr_confidence_gate",
        classification_review_threshold=0.0,
        ocr_review_threshold=0.80,
    )

    inventory = json.loads((candidate / "_manifests" / "inventory.json").read_text(encoding="utf-8"))
    metadata = json.loads((candidate / "scan.metadata.json").read_text(encoding="utf-8"))
    assert summary["needs_review"] == 1
    assert inventory["records"][0]["processing_status"] == "needs_review"
    assert inventory["records"][0]["ocr_confidence"]["value"] == 0.79
    assert metadata["processing_status"] == "needs_review"
    assert "low_ocr_confidence" in metadata["review_reasons"]


def test_pipeline_reviews_llamaparse_pdf_when_ocr_confidence_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "llama.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="llamaparse",
        markdown="# Documento Llama",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="# Documento Llama",
                text_normalized="Documento Llama",
                extraction_method="llamaparse",
                ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[Observation(status="not_detected", value=False, method="test")],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[Observation(status="not_detected", value=False, method="test")],
        ),
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_missing_ocr_confidence",
        classification_review_threshold=0.0,
        ocr_review_threshold=0.80,
    )

    metadata = json.loads((candidate / "llama.metadata.json").read_text(encoding="utf-8"))
    assert summary["needs_review"] == 1
    assert metadata["ocr_confidence"]["kind"] == "unavailable"
    assert "ocr_confidence_unavailable" in metadata["review_reasons"]


def test_pipeline_persists_llama_cloud_metadata_and_confidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    candidate = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    (docs_raw / "llama.pdf").write_bytes(b"%PDF-1.4 fake")

    result = ReadResult(
        extraction_method="llamaparse",
        markdown="# Documento Llama",
        pages=[
            PageRecord(
                page_number=1,
                text_raw="# Documento Llama",
                text_normalized="Documento Llama",
                extraction_method="llamaparse",
                ocr_confidence=ConfidenceMetric(
                    kind="estimated",
                    value=0.91,
                    method="llamaparse_page_parse_confidence",
                    provenance="pjb_123",
                    warnings=["llamaparse_confidence_not_word_ocr_measured"],
                ),
            )
        ],
        tables=TablesArtifact(
            schema_version="2.0",
            document_id="pending",
            table_count=0,
            tables=[],
            page_observations=[Observation(status="not_detected", value=False, method="test")],
        ),
        forms=FormsArtifact(
            schema_version="2.0",
            document_id="pending",
            groups=[],
            page_observations=[Observation(status="not_detected", value=False, method="test")],
        ),
        llama_cloud_metadata=LlamaCloudMetadata(
            parse_job_id="pjb_123",
            parse_status="completed",
            parse_configuration_hash="sha256:parse",
            page_metadata=[
                {
                    "page_number": 1,
                    "confidence": 0.91,
                    "cost_optimized": False,
                }
            ],
            job_metadata={"credits": 2},
        ),
    )
    monkeypatch.setattr(pipeline_module, "_read_document", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        pipeline_module,
        "_handwriting_observation",
        lambda *_args, **_kwargs: Observation(status="not_detected", value=False, method="test"),
    )

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=tmp_path / "data" / "live",
        staging_root=candidate,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_metadata",
        classification_review_threshold=0.0,
        ocr_review_threshold=0.80,
    )

    metadata = json.loads((candidate / "llama.metadata.json").read_text(encoding="utf-8"))
    pages = json.loads((candidate / "llama.pages.json").read_text(encoding="utf-8"))
    assert summary == {"processed": 1, "failed": 0, "needs_review": 0, "skipped": 0}
    assert metadata["ocr_confidence"]["value"] == 0.91
    assert metadata["llama_cloud"]["parse_job_id"] == "pjb_123"
    assert metadata["llama_cloud"]["page_metadata"][0]["confidence"] == 0.91
    assert metadata["llama_cloud"]["job_metadata"] == {"credits": 2}
    assert pages["pages"][0]["ocr_confidence"]["value"] == 0.91


def test_pipeline_writes_llama_phase_events_to_details_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "normalized"
    docs_raw.mkdir(parents=True)
    (docs_raw / "politica.pdf").write_bytes(b"%PDF-1.4 fake")

    class FakeParsing:
        async def parse(self, **_kwargs):
            return {"id": "pjb_observable", "status": "COMPLETED"}

        async def get(self, *_args, **_kwargs):
            return {
                "id": "pjb_observable",
                "status": "COMPLETED",
                "markdown": [
                    {
                        "page": 1,
                        "markdown": "# Politica SST\n\nCodigo SST-PO-01",
                    }
                ],
                "metadata": {"pages": [{"page_number": 1, "confidence": 0.91}]},
                "job_metadata": {"credits": 1},
            }

    class FakeClassify:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, **_kwargs):
            self.calls += 1
            return {
                "id": f"classify_observable_{self.calls}",
                "status": "COMPLETED",
                "label": "politica" if self.calls == 1 else "sg_sst",
                "confidence": 0.96,
                "evidence": [
                    {
                        "page_number": 1,
                        "text": "Politica SST",
                        "source": "llama_classify",
                    }
                ],
            }

    class FakeExtract:
        async def run(self, **_kwargs):
            return {
                "id": "extract_observable",
                "status": "COMPLETED",
                "data": {"code": "SST-PO-01"},
                "evidence": {
                    "code": [
                        {
                            "page_number": 1,
                            "text": "SST-PO-01",
                            "source": "llama_extract",
                        }
                    ]
                },
            }

    class FakeClient:
        def __init__(self) -> None:
            self.parsing = FakeParsing()
            self.classify = FakeClassify()
            self.extract = FakeExtract()

        async def aclose(self) -> None:
            return None

    import ingestion.infrastructure.llama_cloud.client_factory as client_factory

    monkeypatch.setattr(
        client_factory,
        "create_async_llama_cloud_client",
        lambda _settings: FakeClient(),
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
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_phase_logs",
        classification_review_threshold=0.0,
        ocr_review_threshold=0.80,
        llama_settings_override=LlamaSettings(
            cloud_enabled=True,
            api_key="test-key",
            classify_enabled=True,
            extract_enabled=True,
            call_order=("parse", "classify", "extract"),
            local_fallback_enabled=False,
        ),
    )

    events = [
        json.loads(line)
        for line in (normalized / "_manifests" / "llama_phase_logs_details.log")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    llama_events = [
        event for event in events if event.get("stage") == "llama_cloud"
    ]
    assert summary["needs_review"] == 0
    assert [
        (event["event"], event["status"], event["capability"], event.get("job_id"))
        for event in llama_events
    ] == [
        ("llama_parse_start", "started", "parse", None),
        ("llama_parse_finished", "completed", "parse", "pjb_observable"),
        ("llama_classify_start", "started", "classify", None),
        (
            "llama_classify_finished",
            "completed",
            "classify",
            "classify_observable_1,classify_observable_2",
        ),
        ("llama_extract_start", "started", "extract", None),
        ("llama_extract_finished", "completed", "extract", "extract_observable"),
    ]
    assert {event["level"] for event in llama_events} == {"info"}
    assert {event["provider"] for event in llama_events} == {"llama_cloud"}
    assert llama_events[-1]["upstream_job_id"] == "pjb_observable"
    assert llama_events[-1]["result_count"] == 1


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


def test_pipeline_reports_llama_provider_failures_without_local_extractor_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "normalized"
    docs_raw.mkdir(parents=True)
    (docs_raw / "manual.pdf").write_bytes(b"%PDF-1.4")

    def fail_cloud_reader(*_args, **_kwargs):
        raise RuntimeError("provider status COMPLETED did not match internal contract")

    monkeypatch.setattr(pipeline_module, "_read_document", fail_cloud_reader)

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="llama_failure",
        llama_settings_override=LlamaSettings(
            cloud_enabled=True,
            api_key="test-key",
            local_fallback_enabled=False,
        ),
    )

    needs_review = json.loads(
        (normalized / "_manifests" / "needs_review.json").read_text(encoding="utf-8")
    )

    assert summary["needs_review"] == 1
    assert needs_review["items"][0]["reasons"] == ["llama_cloud_provider_error"]
    assert "Llama Cloud" in needs_review["items"][0]["details"][0]


def test_pipeline_configures_region_tesseract_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TESSERACT_CMD", r"C:\Tools\Tesseract\tesseract.exe")
    monkeypatch.setenv("TESSERACT_LANGUAGE", "spa")
    monkeypatch.setenv("TESSERACT_VERSION", "5.4.0")

    engine = _configured_tesseract_engine()

    assert engine.tesseract_cmd == r"C:\Tools\Tesseract\tesseract.exe"
    assert engine.language == "spa"
    assert engine.engine_version == "5.4.0"


def test_pipeline_promotes_without_explicit_golden_pass(
    tmp_path: Path,
) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    live = tmp_path / "data" / "live"
    staging = tmp_path / "data" / "candidate"
    docs_raw.mkdir(parents=True)
    live.mkdir(parents=True)
    (docs_raw / "manual.md").write_text("# Manual\n\nContenido", encoding="utf-8")
    (live / "live.md").write_text("live", encoding="utf-8")

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=live,
        staging_root=staging,
        promote=True,
        golden_status="failed",
        corpus_version="test",
        pipeline_version="2.0.0",
        run_id="structural_promote",
    )

    assert summary["processed"] == 1
    assert (live / "manual.md").exists()
    assert not (live / "live.md").exists()
