from pathlib import Path

import pytest

from ingestion.ocr.ocrmypdf_engine import OcrDependencyError, OcrMyPdfEngine
from ingestion.readers.pdf_digital_reader import MissingPdfExtractor, PdfPage
from ingestion.pipeline import _read_document
from ingestion.schemas.inventory import InventoryRecord


class FakeCompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


class FakeTextExtractor:
    def extract_pages(self, source_path: Path):
        return [
            {
                "page_number": 1,
                "text": "Texto extraido por OCR",
                "confidence": None,
                "contains_handwriting": None,
                "deskew_applied": None,
                "rotation_detected_degrees": None,
            }
        ]


class FakePdfPageExtractor:
    def extract_pages(self, source_path: Path):
        return [PdfPage(page_number=1, text="Texto extraido por OCR", tables=[])]


def test_ocrmypdf_engine_reads_sidecar_text_without_pdf_text_extractor(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        if command[:2] == ["/usr/local/bin/tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.0\n")
        if command[:2] == ["/usr/local/bin/tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="spa\neng\n")
        sidecar_path = Path(command[command.index("--sidecar") + 1])
        sidecar_path.write_text("Pagina uno\fPagina dos", encoding="utf-8")
        return FakeCompletedProcess()

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    engine = OcrMyPdfEngine(
        ocrmypdf_cmd="/usr/local/bin/ocrmypdf",
        tesseract_cmd="/usr/local/bin/tesseract",
        temp_dir=tmp_path,
        runner=runner,
    )

    pages = engine.extract_pages(source)

    assert [page["text"] for page in pages] == ["Pagina uno", "Pagina dos"]
    assert pages[1]["page_number"] == 2
    assert pages[0]["confidence"] is None
    assert pages[1]["confidence"] is None
    assert pages[0]["contains_handwriting"] is None
    assert pages[0]["deskew_applied"] is None
    assert pages[0]["rotation_detected_degrees"] is None


def test_ocrmypdf_engine_runs_with_tesseract_spanish_and_temp_copy(tmp_path: Path) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[:2] == ["/usr/local/bin/tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.0\n")
        if command[:2] == ["/usr/local/bin/tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="List\nspa\neng\n")
        return FakeCompletedProcess()

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    engine = OcrMyPdfEngine(
        ocrmypdf_cmd="/usr/local/bin/ocrmypdf",
        tesseract_cmd="/usr/local/bin/tesseract",
        temp_dir=tmp_path,
        runner=runner,
        text_extractor=FakeTextExtractor(),
    )

    pages = engine.extract_pages(source)

    assert pages[0]["text"] == "Texto extraido por OCR"
    assert pages[0]["confidence"] is None
    assert engine.engine == "tesseract"
    assert engine.engine_version == "5.5.0"
    ocr_call = calls[-1]
    assert ocr_call[:3] == ["/usr/local/bin/ocrmypdf", "--language", "spa"]
    assert "--sidecar" in ocr_call
    assert "--deskew" in ocr_call
    assert "--rotate-pages" in ocr_call
    assert ocr_call[-2] != str(source)


def test_ocrmypdf_engine_pdfpage_fallback_does_not_invent_ocr_metrics(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        if command[:2] == ["/usr/local/bin/tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.0\n")
        if command[:2] == ["/usr/local/bin/tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="spa\neng\n")
        return FakeCompletedProcess()

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    engine = OcrMyPdfEngine(
        ocrmypdf_cmd="/usr/local/bin/ocrmypdf",
        tesseract_cmd="/usr/local/bin/tesseract",
        temp_dir=tmp_path,
        runner=runner,
        text_extractor=FakePdfPageExtractor(),
    )

    pages = engine.extract_pages(source)

    assert pages[0]["confidence"] is None
    assert pages[0]["contains_handwriting"] is None
    assert pages[0]["deskew_applied"] is None
    assert pages[0]["rotation_detected_degrees"] is None


def test_ocrmypdf_engine_reports_missing_spanish_language(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        if command[:2] == ["/usr/local/bin/tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.0\n")
        if command[:2] == ["/usr/local/bin/tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="eng\nosd\n")
        return FakeCompletedProcess()

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    engine = OcrMyPdfEngine(
        ocrmypdf_cmd="/usr/local/bin/ocrmypdf",
        tesseract_cmd="/usr/local/bin/tesseract",
        runner=runner,
        text_extractor=FakeTextExtractor(),
    )

    with pytest.raises(OcrDependencyError) as exc:
        engine.extract_pages(source)

    assert "tesseract_language_missing" in exc.value.reasons


def test_ocrmypdf_engine_reports_timeout(tmp_path: Path) -> None:
    import subprocess

    def runner(command, **kwargs):
        if command[:2] == ["/usr/local/bin/tesseract", "--version"]:
            return FakeCompletedProcess(stdout="tesseract 5.5.0\n")
        if command[:2] == ["/usr/local/bin/tesseract", "--list-langs"]:
            return FakeCompletedProcess(stdout="spa\neng\n")
        raise subprocess.TimeoutExpired(command, timeout=3)

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    engine = OcrMyPdfEngine(
        ocrmypdf_cmd="/usr/local/bin/ocrmypdf",
        tesseract_cmd="/usr/local/bin/tesseract",
        timeout_seconds=3,
        runner=runner,
    )

    with pytest.raises(OcrDependencyError) as exc:
        engine.extract_pages(source)

    assert "ocrmypdf_timeout" in exc.value.reasons


def test_pipeline_falls_back_to_ocr_when_pdf_text_extractor_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    record = InventoryRecord(
        schema_version="2.0",
        document_id="doc_pdf",
        source_relpath="scan.pdf",
        legacy_path=str(source),
        document_name="scan.pdf",
        detected_extension=".pdf",
        reported_extension=".pdf",
        mime_type="application/pdf",
        content_hash="abc",
        file_size=source.stat().st_size,
        ingestion_date="2026-07-16T00:00:00-05:00",
        category_inferred="copasst",
        pipeline_version="1.0.0",
        corpus_version="test",
    )

    result = _read_document(
        record,
        pdf_reader_factory=lambda: MissingPdfExtractor(),
        ocr_engine=FakeTextExtractor(),
    )

    assert result.extraction_method == "ocr"
    assert result.pages[0].text_normalized == "Texto extraido por OCR"
