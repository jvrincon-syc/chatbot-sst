from pathlib import Path

import pytest

from ingestion.ocr.rasterizer import RasterRegion
from ingestion.ocr.tesseract_engine import (
    TesseractEngine,
    TesseractPdfEngine,
    parse_tesseract_tsv,
)
from ingestion.schemas.common import BBox


TSV = """level	page_num	block_num	par_num	line_num	word_num	left	top	width	height	conf	text
5	1	1	1	1	1	10	20	30	10	96	Texto
5	1	1	1	1	2	50	20	40	10	63	bajo
5	1	1	1	1	3	90	20	10	10	-1	
"""


def test_tesseract_tsv_parser_keeps_only_real_word_confidences() -> None:
    result = parse_tesseract_tsv(TSV, page_number=2, engine_version="5.5.2")

    assert result.page_number == 2
    assert result.text == "Texto bajo"
    assert [word.text for word in result.words] == ["Texto", "bajo"]
    assert result.words[0].confidence == 0.96
    assert result.words[0].bbox == BBox(
        x0=10,
        top=20,
        x1=40,
        bottom=30,
        coordinate_system="pixels",
    )
    assert result.confidence.kind == "measured"
    assert result.confidence.value == pytest.approx(0.795)
    assert result.confidence.unit == "mean_word_confidence"
    assert result.confidence.sample_size == 2
    assert result.low_confidence_word_count == 1


def test_tesseract_tsv_parser_does_not_merge_rows_after_ocr_quotes() -> None:
    tsv = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96\t\"Texto
5\t1\t1\t1\t1\t2\t50\t20\t40\t10\t97\tsiguiente
"""

    result = parse_tesseract_tsv(tsv, page_number=1, engine_version="5.5.2")

    assert [word.text for word in result.words] == ['"Texto', "siguiente"]
    assert "5\t1\t1" not in result.text


def test_tesseract_tsv_parser_reconstructs_ocr_lines() -> None:
    tsv = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96\tLinea
5\t1\t1\t1\t1\t2\t50\t20\t40\t10\t97\tuno
5\t1\t1\t1\t2\t1\t10\t40\t30\t10\t98\tLinea
5\t1\t1\t1\t2\t2\t50\t40\t40\t10\t99\tdos
"""

    result = parse_tesseract_tsv(tsv, page_number=1, engine_version="5.5.2")

    assert result.text == "Linea uno\nLinea dos"


def test_tesseract_tsv_without_words_has_unavailable_confidence() -> None:
    result = parse_tesseract_tsv(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n",
        page_number=1,
    )

    assert result.words == []
    assert result.confidence.kind == "unavailable"
    assert result.confidence.value is None


def test_tesseract_engine_invokes_tsv_mode_and_parses_stdout(tmp_path: Path) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))

        class Result:
            stdout = TSV

        return Result()

    image = tmp_path / "region.png"
    image.write_bytes(b"fake")
    region = RasterRegion(
        image_path=image,
        page_number=1,
        bbox=BBox(x0=0, top=0, x1=100, bottom=40, coordinate_system="pixels"),
        dpi=300,
        width=100,
        height=40,
    )

    result = TesseractEngine(
        tesseract_cmd="/usr/local/bin/tesseract",
        language="spa",
        engine_version="5.5.2",
        runner=runner,
    ).recognize(region)

    assert calls[0][0] == ["/usr/local/bin/tesseract", str(image), "stdout", "-l", "spa", "tsv"]
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "replace"
    assert result.confidence.kind == "measured"
    assert result.bbox == region.bbox


def test_tesseract_engine_adds_extra_args_before_tsv_config(tmp_path: Path) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(command)

        class Result:
            stdout = TSV

        return Result()

    image = tmp_path / "region.png"
    image.write_bytes(b"fake")
    region = RasterRegion(
        image_path=image,
        page_number=1,
        dpi=300,
        width=100,
        height=100,
    )

    TesseractEngine(
        tesseract_cmd="/usr/local/bin/tesseract",
        language="spa",
        engine_version="5.5.2",
        extra_args=("--psm", "6"),
        runner=runner,
    ).recognize(region)

    assert calls[0] == [
        "/usr/local/bin/tesseract",
        str(image),
        "stdout",
        "-l",
        "spa",
        "--psm",
        "6",
        "tsv",
    ]


def test_tesseract_engine_can_return_plain_text_for_header_supplement(
    tmp_path: Path,
) -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(command)

        class Result:
            stdout = "Versión [02\n"

        return Result()

    image = tmp_path / "region.png"
    image.write_bytes(b"fake")
    region = RasterRegion(
        image_path=image,
        page_number=1,
        dpi=300,
        width=100,
        height=100,
    )

    text = TesseractEngine(
        tesseract_cmd="/usr/local/bin/tesseract",
        language="spa",
        engine_version="5.5.2",
        extra_args=("--psm", "6"),
        runner=runner,
    ).recognize_text(region)

    assert text == "Versión [02"
    assert calls[0] == [
        "/usr/local/bin/tesseract",
        str(image),
        "stdout",
        "-l",
        "spa",
        "--psm",
        "6",
    ]


def test_tesseract_pdf_engine_extracts_every_page_with_measured_confidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF fake")

    class FakeRasterizer:
        def render(self, path, page_number, clip=None):
            image = tmp_path / f"page-{page_number}.png"
            image.write_bytes(b"png")
            return RasterRegion(
                image_path=image,
                page_number=page_number,
                dpi=300,
                width=100,
                height=100,
            )

    class FakeRegionEngine:
        engine = "tesseract"
        engine_version = "5.4.0"
        language = "spa"

        def recognize(self, region):
            return parse_tesseract_tsv(
                TSV.replace("Texto", f"Pagina{region.page_number}"),
                page_number=region.page_number,
                engine_version=self.engine_version,
            )

    pages = TesseractPdfEngine(
        region_engine=FakeRegionEngine(),
        rasterizer=FakeRasterizer(),
        page_count=lambda _path: 2,
    ).extract_pages(source)

    assert [page["page_number"] for page in pages] == [1, 2]
    assert [page["text"] for page in pages] == ["Pagina1 bajo", "Pagina2 bajo"]
    assert all(page["confidence"] == pytest.approx(0.795) for page in pages)


def test_tesseract_pdf_engine_appends_control_header_ocr_when_unique(
    tmp_path: Path,
) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF fake")

    class FakeRasterizer:
        def render(self, path, page_number, clip=None, dpi=None):
            image = tmp_path / f"page-{page_number}-{clip is not None}.png"
            image.write_bytes(b"png")
            return RasterRegion(
                image_path=image,
                page_number=page_number,
                bbox=clip,
                dpi=dpi or 300,
                width=100,
                height=100,
            )

    class FakeRegionEngine:
        engine = "tesseract"
        engine_version = "5.5.2"
        language = "spa"

        def __init__(self, extra_args=()):
            self.extra_args = tuple(extra_args)

        def with_extra_args(self, extra_args):
            return FakeRegionEngine(extra_args)

        def recognize(self, region):
            text = "Texto base"
            if self.extra_args == ("--psm", "6"):
                text = "Versión 0.2"
            return parse_tesseract_tsv(
                TSV.replace("Texto", text.split()[0]).replace("bajo", text.split()[-1]),
                page_number=region.page_number,
                engine_version=self.engine_version,
            )

        def recognize_text(self, region):
            return "Versión 0.2" if self.extra_args == ("--psm", "6") else ""

    pages = TesseractPdfEngine(
        region_engine=FakeRegionEngine(),
        rasterizer=FakeRasterizer(),
        page_count=lambda _path: 1,
        page_size=lambda _path, _page_number: (100.0, 200.0),
    ).extract_pages(source)

    assert "Texto base" in pages[0]["text"]
    assert "Versión 0.2" in pages[0]["text"]
