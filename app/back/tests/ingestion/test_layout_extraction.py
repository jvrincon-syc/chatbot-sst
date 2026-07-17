from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ingestion.layout.models import PDF_POINT_COORDINATE_SYSTEM, LayoutBlock, LayoutPage
from ingestion.layout.pdfplumber_extractor import (
    LayoutCapabilityUnavailableError,
    PdfLayoutExtractor,
)
from ingestion.schemas.common import BBox


class FakePdf:
    def __init__(self, pages: list[Any]) -> None:
        self.pages = pages

    def __enter__(self) -> "FakePdf":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakePdfPlumber:
    def __init__(self, pages: list[Any]) -> None:
        self.pages = pages
        self.opened_path: str | None = None

    def open(self, path: str) -> FakePdf:
        self.opened_path = path
        return FakePdf(self.pages)


class FakePage:
    width = 612
    height = 792
    cropbox = (0, 0, 612, 792)
    rotation = 90

    def __init__(self) -> None:
        self.images = [
            {"x0": 200, "top": 80, "x1": 260, "bottom": 140, "name": "logo"}
        ]
        self.lines = [
            {"x0": 10, "top": 120, "x1": 300, "bottom": 121, "linewidth": 1}
        ]
        self.rects = [
            {"x0": 30, "top": 180, "x1": 220, "bottom": 240, "stroke": True}
        ]

    def extract_text(self, **kwargs: object) -> str:
        assert kwargs == {"layout": True}
        return "  Titulo SST  \nLinea sin normalizar"

    def extract_words(self, **kwargs: object) -> list[dict[str, object]]:
        assert kwargs["keep_blank_chars"] is True
        return [
            {"text": "segundo", "x0": 120, "top": 50, "x1": 170, "bottom": 62},
            {"text": "  Titulo SST  ", "x0": 20, "top": 50, "x1": 100, "bottom": 62},
        ]


def test_pdfplumber_layout_extractor_preserves_page_geometry_and_raw_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "documento.pdf"
    source.write_bytes(b"%PDF-1.4 fake")
    fake_module = FakePdfPlumber([FakePage()])

    pages = PdfLayoutExtractor(pdfplumber_module=fake_module).extract_pages(source)

    assert fake_module.opened_path == str(source)
    assert len(pages) == 1
    page = pages[0]
    assert page.page_number == 1
    assert page.width == 612
    assert page.height == 792
    assert page.rotation == 90
    assert page.cropbox == BBox(
        x0=0,
        top=0,
        x1=612,
        bottom=792,
        coordinate_system=PDF_POINT_COORDINATE_SYSTEM,
    )
    assert page.text_raw == "  Titulo SST  \nLinea sin normalizar"


def test_pdfplumber_layout_extractor_emits_supported_block_types_in_reading_order(
    tmp_path: Path,
) -> None:
    fake_module = FakePdfPlumber([FakePage()])

    page = PdfLayoutExtractor(pdfplumber_module=fake_module).extract_pages(
        tmp_path / "a.pdf"
    )[0]

    assert [block.block_type for block in page.blocks] == [
        "text",
        "text",
        "image",
        "line",
        "rect",
    ]
    assert [block.reading_order for block in page.blocks] == [0, 1, 2, 3, 4]
    assert [block.block_id for block in page.blocks] == [
        "p1_text_0000",
        "p1_text_0001",
        "p1_image_0002",
        "p1_line_0003",
        "p1_rect_0004",
    ]
    assert page.blocks[0].text == "  Titulo SST  "
    assert page.blocks[0].bbox.x0 == 20
    assert page.blocks[0].bbox.top == 50
    assert page.blocks[0].bbox.coordinate_system == PDF_POINT_COORDINATE_SYSTEM
    assert page.blocks[2].raw_attributes["name"] == "logo"
    assert page.blocks[3].source == "pdfplumber.lines"
    assert page.blocks[4].source == "pdfplumber.rects"


def test_layout_extractor_converts_y_coordinates_to_top_left_pdf_points(
    tmp_path: Path,
) -> None:
    class YCoordinatePage(FakePage):
        rotation = 0

        def __init__(self) -> None:
            self.images = []
            self.lines = [{"x0": 10, "x1": 20, "y0": 700, "y1": 720}]
            self.rects = []

        def extract_words(self, **_kwargs: object) -> list[dict[str, object]]:
            return []

    page = PdfLayoutExtractor(
        pdfplumber_module=FakePdfPlumber([YCoordinatePage()])
    ).extract_pages(tmp_path / "a.pdf")[0]

    assert page.blocks[0].bbox == BBox(
        x0=10,
        top=72,
        x1=20,
        bottom=92,
        coordinate_system=PDF_POINT_COORDINATE_SYSTEM,
    )


def test_layout_models_reject_non_pdf_point_geometry_and_unsorted_order() -> None:
    with pytest.raises(ValidationError):
        LayoutBlock(
            block_id="b1",
            block_type="text",
            bbox=BBox(x0=0, top=0, x1=1, bottom=1, coordinate_system="pixels"),
            reading_order=0,
            text="texto",
            source="test",
        )

    block_late = LayoutBlock(
        block_id="b2",
        block_type="text",
        bbox=BBox(
            x0=0,
            top=0,
            x1=10,
            bottom=10,
            coordinate_system=PDF_POINT_COORDINATE_SYSTEM,
        ),
        reading_order=1,
        text="tarde",
        source="test",
    )
    block_early = block_late.model_copy(
        update={"block_id": "b3", "reading_order": 0, "text": "temprano"}
    )
    with pytest.raises(ValidationError):
        LayoutPage(
            page_number=1,
            width=100,
            height=100,
            cropbox=BBox(
                x0=0,
                top=0,
                x1=100,
                bottom=100,
                coordinate_system=PDF_POINT_COORDINATE_SYSTEM,
            ),
            blocks=[block_late, block_early],
        )


def test_layout_extractor_raises_capability_unavailable_when_pdfplumber_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> Any:
        if name == "pdfplumber":
            raise ImportError("missing pdfplumber")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(LayoutCapabilityUnavailableError, match="pdfplumber is unavailable"):
        PdfLayoutExtractor().extract_pages(Path("missing.pdf"))
