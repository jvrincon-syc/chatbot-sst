from pathlib import Path

from ingestion.classification.rules import classify_document
from ingestion.pipeline import run_pipeline


def test_classification_uses_path_name_and_heading_patterns() -> None:
    result = classify_document(
        Path("data/docs_raw/general_sst/manuales/politica/politica.md"),
        "# Politica de seguridad y salud en el trabajo\n\nContenido",
    )

    assert result["document_type"] == "politica"
    assert result["topic"] == "Politica de seguridad"
    assert result["classification_confidence"] >= 0.80
    assert result["reasons"]


def test_classification_identifies_form_documents() -> None:
    result = classify_document(
        Path("data/docs_raw/general_sst/formularios/FR-SST-01.md"),
        "# Formato de inspeccion\n\nCodigo FR-SST-01",
    )

    assert result["document_type"] == "formulario"
    assert result["topic"] == "Formularios"
    assert result["classification_confidence"] >= 0.80


def test_pipeline_marks_ambiguous_classification_as_needs_review(tmp_path: Path) -> None:
    docs_raw = tmp_path / "data" / "docs_raw"
    normalized = tmp_path / "data" / "docs_normalized"
    docs_raw.mkdir(parents=True)
    (docs_raw / "nota.md").write_text("# Nota\n\nContenido generico sin senales del dominio.", encoding="utf-8")

    summary = run_pipeline(
        docs_raw=docs_raw,
        docs_normalized=normalized,
        corpus_version="test",
        pipeline_version="1.0.0",
        run_id="classification_test",
        classification_review_threshold=0.60,
    )

    assert summary["needs_review"] == 1
    metadata = (normalized / "nota.metadata.json").read_text(encoding="utf-8")
    assert '"classification_confidence": 0.45' in metadata
    needs_review = (normalized / "_manifests" / "needs_review.json").read_text(encoding="utf-8")
    assert "ambiguous_classification" in needs_review
