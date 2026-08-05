from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ingestion.ocr.mock_engine import MockOcrEngine
from ingestion.ocr.tesseract_engine import parse_tesseract_tsv
from ingestion.domain.models.parsed_document import ParsedDocument, ParsedPage
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.domain.models.llama_understanding import LlamaPipelineResult, LlamaUnderstanding
from ingestion.readers.markdown_reader import MarkdownReader
from ingestion.readers.base import ReadResult
from ingestion.readers.hybrid_reader import HybridReader
from ingestion.readers.llama_parse_reader import LlamaParseReader
from ingestion.readers.pdf_digital_reader import PdfDigitalReader, PdfPage
from ingestion.schemas.artifacts import FormsArtifact, PageRecord, TablesArtifact
from ingestion.schemas.common import BBox, ConfidenceMetric, Observation, PageBlock
from ingestion.readers.pdf_scanned_reader import PdfScannedReader
from datetime import datetime, timezone


class FakePdfExtractor:
    def extract_pages(self, source_path: Path) -> list[PdfPage]:
        return [
            PdfPage(page_number=1, text="Titulo\n\nPrimer parrafo", tables=[]),
            PdfPage(page_number=2, text="Segundo parrafo", tables=[]),
        ]


def _provider_job(capability: str, job_id: str) -> ProviderJobRef:
    now = datetime.now(timezone.utc)
    return ProviderJobRef(
        provider="llama_cloud",
        capability=capability,
        job_id=job_id,
        status="completed",
        configuration_hash="sha256:config",
        created_at=now,
        completed_at=now,
    )


class FakeParseAdapter:
    async def parse(self, request):
        return ParsedDocument(
            provider_job=_provider_job("parse", "pjb_reader"),
            markdown_pages=[ParsedPage(page_number=1, markdown="# Formato")],
        )


class FakeLlamaOrchestrator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, *, document_id, source_path, source_hash, mime_type):
        self.calls.append(document_id)
        parsed = ParsedDocument(
            provider_job=_provider_job("parse", "pjb_reader"),
            markdown_pages=[ParsedPage(page_number=1, markdown="# Formato")],
        )
        return LlamaPipelineResult(
            parsed=parsed,
            understanding=LlamaUnderstanding(
                parse_job_id="pjb_reader",
                schema_extract="formulario_document_control",
            ),
        )


class FakeAsyncCloser:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeAsyncAcloser:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def test_llama_parse_reader_runs_orchestrator_after_parse(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF")
    orchestrator = FakeLlamaOrchestrator()

    result = LlamaParseReader(
        adapter=FakeParseAdapter(),
        configuration_hash="sha256:parse",
        orchestrator=orchestrator,
    ).read(source, document_id="doc_123", source_hash="sha256:source")

    assert orchestrator.calls == ["doc_123"]
    assert result.llama_understanding is not None
    assert result.llama_understanding.parse_job_id == "pjb_reader"
    assert "llama_parse_job:pjb_reader" in result.warnings


def test_llama_parse_reader_closes_async_client_after_orchestrator_run(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF")
    closer = FakeAsyncCloser()

    LlamaParseReader(
        adapter=FakeParseAdapter(),
        configuration_hash="sha256:parse",
        orchestrator=FakeLlamaOrchestrator(),
        async_client=closer,
    ).read(source, document_id="doc_123", source_hash="sha256:source")

    assert closer.closed is True


def test_llama_parse_reader_closes_async_client_with_aclose(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF")
    closer = FakeAsyncAcloser()

    LlamaParseReader(
        adapter=FakeParseAdapter(),
        configuration_hash="sha256:parse",
        orchestrator=FakeLlamaOrchestrator(),
        async_client=closer,
    ).read(source, document_id="doc_123", source_hash="sha256:source")

    assert closer.closed is True


def test_markdown_reader_preserves_title_list_and_table(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"
    source.write_text(
        "# Manual\n\n- item uno\n- item dos\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
        encoding="utf-8",
    )

    result = MarkdownReader().read(source)

    assert result.extraction_method == "markdown"
    assert result.page_count == 1
    assert result.pages[0].text_raw.startswith("# Manual")
    assert "| A | B |" in result.pages[0].text_normalized
    assert result.pages[0].ocr_confidence.kind == "unavailable"
    assert result.warnings == []


def test_markdown_reader_missing_title_is_warning_not_review_blocker(tmp_path: Path) -> None:
    source = tmp_path / "nota.md"
    source.write_text("Contenido sin encabezado", encoding="utf-8")

    result = MarkdownReader().read(source)

    assert result.warnings == ["missing_title"]
    assert result.review_reasons == []


def test_pdf_digital_reader_uses_injected_extractor_and_adds_page_markers(tmp_path: Path) -> None:
    source = tmp_path / "documento.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = PdfDigitalReader(extractor=FakePdfExtractor(), min_extractable_words=1).read(source)

    assert result.extraction_method == "pdf_digital"
    assert result.page_count == 2
    assert "<!-- page: 1 -->" in result.markdown
    assert "<!-- page: 2 -->" in result.markdown
    assert result.pages[1].page_number == 2
    assert result.pages[0].ocr_confidence.kind == "unavailable"


def test_pdf_digital_reader_evaluates_table_and_form_capabilities(tmp_path: Path) -> None:
    class StructuredPdfExtractor:
        def extract_pages(self, source_path: Path) -> list[PdfPage]:
            return [
                PdfPage(
                    page_number=1,
                    text="FORMATO DE QUEJA\nNombre:\nDescripcion:",
                    tables=[
                        {
                            "bbox": (20, 100, 500, 180),
                            "rows": [
                                ["Campo", "Valor"],
                                ["Nombre", ""],
                            ],
                        }
                    ],
                    blocks=[
                        PageBlock(
                            block_id="name",
                            text="Nombre:",
                            bbox=BBox(
                                x0=20,
                                top=200,
                                x1=90,
                                bottom=218,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="label",
                        ),
                        PageBlock(
                            block_id="description",
                            text="Descripcion:",
                            bbox=BBox(
                                x0=20,
                                top=240,
                                x1=120,
                                bottom=258,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="label",
                        ),
                        PageBlock(
                            block_id="blank",
                            text="",
                            bbox=BBox(
                                x0=130,
                                top=240,
                                x1=500,
                                bottom=300,
                                coordinate_system="pdf_points",
                            ),
                            extraction_method="pdf_digital",
                            role="blank_area",
                        ),
                    ],
                )
            ]

    source = tmp_path / "structured.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = PdfDigitalReader(
        extractor=StructuredPdfExtractor(),
        min_extractable_words=1,
    ).read(source)

    assert result.tables is not None
    assert result.tables.table_count == 1
    assert result.tables.page_observations[0].status == "detected"
    assert result.forms is not None
    assert result.forms.page_observations[0].status == "detected"


def test_hybrid_reader_preserves_forms_from_digital_reader_when_ocr_adds_text(tmp_path: Path) -> None:
    class FakeDigitalReader:
        def read(self, source_path: Path) -> ReadResult:
            return ReadResult(
                extraction_method="pdf_digital",
                markdown="texto digital",
                pages=[
                    PageRecord(
                        page_number=1,
                        text_raw="texto digital",
                        text_normalized="texto digital",
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

    class FakeCoverageAnalyzer:
        def assess(self, page):
            return SimpleNamespace(
                candidate_regions=[
                    SimpleNamespace(page_number=page.page_number, bbox=None)
                ]
            )

    class FakeRasterizer:
        def render(self, source_path, page_number, bbox):
            return SimpleNamespace(
                image_path=source_path,
                page_number=page_number,
                bbox=bbox,
                dpi=300,
                width=100,
                height=30,
            )

    class FakeOcrEngine:
        engine_version = "5.5.2"
        language = "spa"

        def recognize(self, region):
            return parse_tesseract_tsv(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
                "5\t1\t1\t1\t1\t1\t0\t0\t20\t10\t96\tadicional\n",
                page_number=region.page_number,
                engine_version=self.engine_version,
            )

    source = tmp_path / "hybrid.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = HybridReader(
        digital_reader=FakeDigitalReader(),
        coverage_analyzer=FakeCoverageAnalyzer(),
        rasterizer=FakeRasterizer(),
        ocr_engine=FakeOcrEngine(),
    ).read(source)

    assert result.extraction_method == "hybrid"
    assert result.forms is not None
    assert result.forms.page_observations[0].status == "not_detected"


def test_hybrid_reader_keeps_digital_method_when_ocr_adds_no_unique_text(
    tmp_path: Path,
) -> None:
    class FakeDigitalReader:
        def read(self, source_path: Path) -> ReadResult:
            return ReadResult(
                extraction_method="pdf_digital",
                markdown="texto digital",
                pages=[
                    PageRecord(
                        page_number=1,
                        text_raw="texto digital",
                        text_normalized="texto digital",
                        extraction_method="pdf_digital",
                        ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
                    )
                ],
            )

    class FakeCoverageAnalyzer:
        def assess(self, page):
            return SimpleNamespace(
                candidate_regions=[
                    SimpleNamespace(page_number=page.page_number, bbox=None)
                ]
            )

    class FakeRasterizer:
        def render(self, source_path, page_number, bbox):
            return SimpleNamespace(
                image_path=source_path,
                page_number=page_number,
                bbox=bbox,
                dpi=300,
                width=100,
                height=30,
            )

    class FakeOcrEngine:
        engine_version = "5.5.2"
        language = "spa"

        def recognize(self, region):
            return parse_tesseract_tsv(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
                "5\t1\t1\t1\t1\t1\t0\t0\t20\t10\t96\ttexto\n"
                "5\t1\t1\t1\t1\t2\t25\t0\t20\t10\t96\tdigital\n",
                page_number=region.page_number,
                engine_version=self.engine_version,
            )

    source = tmp_path / "hybrid.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    result = HybridReader(
        digital_reader=FakeDigitalReader(),
        coverage_analyzer=FakeCoverageAnalyzer(),
        rasterizer=FakeRasterizer(),
        ocr_engine=FakeOcrEngine(),
    ).read(source)

    assert result.extraction_method == "pdf_digital"
    assert result.pages[0].extraction_method == "pdf_digital"


def test_pdf_digital_reader_rejects_pdf_without_enough_text(tmp_path: Path) -> None:
    class EmptyPdfExtractor:
        def extract_pages(self, source_path: Path) -> list[PdfPage]:
            return [PdfPage(page_number=1, text="", tables=[])]

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    try:
        PdfDigitalReader(extractor=EmptyPdfExtractor()).read(source)
    except RuntimeError as exc:
        assert "PDF text layer insufficient" in str(exc)
    else:
        raise AssertionError("Expected scanned PDF fallback signal")


def test_pdf_scanned_reader_uses_mock_ocr_engine_and_flags_low_confidence(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake scan")
    engine = MockOcrEngine(
        pages=[
            {
                "page_number": 1,
                "text": "Texto OCR",
                "confidence": 0.42,
                "contains_handwriting": True,
            }
        ]
    )

    result = PdfScannedReader(ocr_engine=engine, low_confidence_threshold=0.70).read(source)

    assert result.extraction_method == "ocr"
    assert result.page_count == 1
    assert result.ocr is not None
    assert result.ocr.document_confidence.value == 0.42
    assert result.pages[0].ocr_confidence.value == 0.42
    assert "low_ocr_confidence" in result.review_reasons
    assert "possible_handwriting" in result.review_reasons


def test_pdf_scanned_reader_evaluates_text_tables_and_forms(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake scan")
    engine = MockOcrEngine(
        pages=[
            {
                "page_number": 1,
                "text": (
                    "CODIGO PL.RH-01-SST | CLASIFICACION | USO INTERNO\n"
                    "Politica sin campos diligenciables"
                ),
                "confidence": 0.91,
            }
        ]
    )

    result = PdfScannedReader(ocr_engine=engine).read(source)

    assert result.tables is not None
    assert result.tables.table_count == 1
    assert result.tables.page_observations[0].status == "detected"
    assert result.forms is not None
    assert result.forms.page_observations[0].status == "not_detected"


def test_pdf_scanned_reader_rejects_boolean_confidence_before_numeric_coercion(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4 fake scan")
    engine = MockOcrEngine(
        pages=[
            {
                "page_number": 1,
                "text": "Texto OCR",
                "confidence": True,
            }
        ]
    )

    result = PdfScannedReader(ocr_engine=engine, low_confidence_threshold=0.70).read(source)

    assert result.pages[0].ocr_confidence.kind == "unavailable"
    assert result.ocr is not None
    assert result.ocr.document_confidence.kind == "unavailable"
    assert "boolean_ocr_confidence_rejected" in result.review_reasons
