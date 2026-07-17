from pathlib import Path

import pytest
from pypdf import PdfReader

from ingestion.ocr.doctor import check_ocr_environment
from ingestion.pipeline import run_pipeline
from ingestion.validation.golden import load_golden, validate_pdf_corpus
from ingestion.validation.normalized import validate_normalized_tree


RAW_ROOT = Path("data/docs_raw")
GOLDEN_PATH = Path("docs/ingestion/pdf_corpus_expected.json")


@pytest.mark.corpus
def test_audited_pdf_sources_are_exactly_nine_documents_and_77_pages() -> None:
    golden = load_golden(GOLDEN_PATH)
    actual_sources = {
        path.relative_to(RAW_ROOT).as_posix()
        for path in RAW_ROOT.rglob("*.pdf")
    }
    expected_sources = {
        document.source_relpath
        for document in golden.documents
    }

    assert actual_sources == expected_sources
    actual_pages = sum(
        len(PdfReader(RAW_ROOT / source).pages)
        for source in sorted(actual_sources)
    )
    assert actual_pages == 77


@pytest.mark.corpus
def test_audited_pdf_candidate_passes_structural_and_semantic_gates(
    tmp_path: Path,
) -> None:
    capabilities = check_ocr_environment()
    required_ocr = (
        capabilities.ocrmypdf_available
        and capabilities.tesseract_available
        and capabilities.language_available
        and capabilities.ghostscript_available
    )
    if not required_ocr:
        pytest.skip(
            "real corpus closure blocked by capabilities: "
            + ", ".join(capabilities.issues)
        )

    golden = load_golden(GOLDEN_PATH)
    candidate = tmp_path / "candidate"
    run_pipeline(
        docs_raw=RAW_ROOT,
        docs_normalized=tmp_path / "live",
        staging_root=candidate,
        only_sources=[
            document.source_relpath
            for document in golden.documents
        ],
        force=True,
        corpus_version="1",
        pipeline_version="2.0.0",
        run_id="corpus_golden",
    )

    structural = validate_normalized_tree(
        candidate,
        raw_root=RAW_ROOT,
        mode="closure",
        run_id="corpus_golden",
    )
    semantic = validate_pdf_corpus(candidate, RAW_ROOT, golden)

    assert structural.status == "passed"
    assert semantic.status == "passed"
