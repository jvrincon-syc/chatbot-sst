from pathlib import Path

import pytest

from ingestion.ocr.rasterizer import RasterRegion
from ingestion.ocr.tesseract_engine import TesseractEngine, parse_tesseract_tsv
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
        calls.append(command)

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

    assert calls[0] == ["/usr/local/bin/tesseract", str(image), "stdout", "-l", "spa", "tsv"]
    assert result.confidence.kind == "measured"
    assert result.bbox == region.bbox
