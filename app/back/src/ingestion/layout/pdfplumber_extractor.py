from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Iterable

from ingestion.layout.models import (
    PDF_POINT_COORDINATE_SYSTEM,
    LayoutBlock,
    LayoutBlockType,
    LayoutPage,
)
from ingestion.schemas.common import BBox


class LayoutCapabilityUnavailableError(RuntimeError):
    """Raised when the digital layout backend is not installed."""


class PdfLayoutExtractor:
    def __init__(self, pdfplumber_module: Any | None = None) -> None:
        self._pdfplumber_module = pdfplumber_module

    def extract_pages(self, path: Path) -> list[LayoutPage]:
        pdfplumber = self._load_pdfplumber()
        with pdfplumber.open(str(path)) as pdf:
            return [
                self._extract_page(page=page, page_number=index)
                for index, page in enumerate(pdf.pages, start=1)
            ]

    def _load_pdfplumber(self) -> Any:
        if self._pdfplumber_module is not None:
            return self._pdfplumber_module
        try:
            return importlib.import_module("pdfplumber")
        except ImportError as exc:
            raise LayoutCapabilityUnavailableError(
                "pdfplumber is unavailable; install pdfplumber to evaluate digital PDF layout."
            ) from exc

    def _extract_page(self, page: Any, page_number: int) -> LayoutPage:
        width = float(getattr(page, "width"))
        height = float(getattr(page, "height"))
        cropbox = _cropbox(getattr(page, "cropbox", None), width=width, height=height)
        text_raw = _extract_text(page)
        block_candidates = [
            *_text_candidates(page),
            *_object_candidates(page, "images", "image"),
            *_object_candidates(page, "lines", "line"),
            *_object_candidates(page, "rects", "rect"),
        ]
        blocks = _ordered_blocks(
            block_candidates,
            page_number=page_number,
            page_height=height,
        )

        return LayoutPage(
            page_number=page_number,
            width=width,
            height=height,
            cropbox=cropbox,
            rotation=int(getattr(page, "rotation", 0) or 0),
            text_raw=text_raw,
            blocks=blocks,
            tables=_table_candidates(page),
        )


def _extract_text(page: Any) -> str:
    extract_text = getattr(page, "extract_text", None)
    if extract_text is None:
        return ""
    try:
        return extract_text(layout=True) or ""
    except TypeError:
        return extract_text() or ""


def _table_candidates(page: Any) -> list[dict[str, Any]]:
    finder = getattr(page, "find_tables", None)
    if not callable(finder):
        return []
    candidates: list[dict[str, Any]] = []
    for table in finder() or []:
        extract = getattr(table, "extract", None)
        rows = extract() if callable(extract) else []
        if not rows:
            continue
        bbox = getattr(table, "bbox", None)
        if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
            continue
        candidates.append(
            {
                "bbox": tuple(float(value) for value in bbox),
                "rows": [
                    [str(cell or "").strip() for cell in row]
                    for row in rows
                ],
            }
        )
    return candidates


def _text_candidates(page: Any) -> list[dict[str, Any]]:
    extract_words = getattr(page, "extract_words", None)
    if extract_words is None:
        return []
    try:
        words = extract_words(
            keep_blank_chars=True,
            use_text_flow=False,
            extra_attrs=[],
        )
    except TypeError:
        words = extract_words()

    candidates: list[dict[str, Any]] = []
    for word in words or []:
        text = str(word.get("text", ""))
        candidates.append(
            {
                "block_type": "text",
                "bbox": word,
                "text": text,
                "source": "pdfplumber.word",
                "raw_attributes": dict(word),
            }
        )
    return candidates


def _object_candidates(
    page: Any,
    attr_name: str,
    block_type: LayoutBlockType,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in _as_iterable(getattr(page, attr_name, [])):
        candidates.append(
            {
                "block_type": block_type,
                "bbox": item,
                "text": None,
                "source": f"pdfplumber.{attr_name}",
                "raw_attributes": dict(item),
            }
        )
    return candidates


def _as_iterable(value: Any) -> Iterable[dict[str, Any]]:
    if value is None:
        return []
    return value


def _ordered_blocks(
    candidates: list[dict[str, Any]],
    *,
    page_number: int,
    page_height: float,
) -> list[LayoutBlock]:
    typed_candidates = []
    for index, candidate in enumerate(candidates):
        bbox, warnings = _bbox_from_object(candidate["bbox"], page_height=page_height)
        typed_candidates.append(
            (
                bbox.top,
                bbox.x0,
                _type_order(candidate["block_type"]),
                index,
                bbox,
                warnings,
                candidate,
            )
        )

    blocks: list[LayoutBlock] = []
    for reading_order, (_, _, _, _, bbox, warnings, candidate) in enumerate(
        sorted(typed_candidates)
    ):
        block_type: LayoutBlockType = candidate["block_type"]
        blocks.append(
            LayoutBlock(
                block_id=f"p{page_number}_{block_type}_{reading_order:04d}",
                block_type=block_type,
                bbox=bbox,
                reading_order=reading_order,
                text=candidate["text"],
                source=candidate["source"],
                raw_attributes=candidate["raw_attributes"],
                warnings=warnings,
            )
        )
    return blocks


def _type_order(block_type: str) -> int:
    return {
        "text": 0,
        "image": 1,
        "line": 2,
        "rect": 3,
    }[block_type]


def _cropbox(raw_cropbox: Any, *, width: float, height: float) -> BBox:
    if raw_cropbox is None:
        values = (0.0, 0.0, width, height)
    else:
        values = tuple(raw_cropbox)
        if len(values) != 4:
            raise ValueError("pdf page cropbox must contain four numeric coordinates")
    x0, top, x1, bottom = (float(value) for value in values)
    return _bbox_from_coordinates(x0=x0, top=top, x1=x1, bottom=bottom)[0]


def _bbox_from_object(raw: dict[str, Any], *, page_height: float) -> tuple[BBox, list[str]]:
    x0 = raw.get("x0")
    x1 = raw.get("x1")
    top = raw.get("top")
    bottom = raw.get("bottom")

    if top is None or bottom is None:
        y0 = raw.get("y0")
        y1 = raw.get("y1")
        if y0 is None or y1 is None:
            raise ValueError("layout object bbox requires top/bottom or y0/y1 coordinates")
        top = page_height - float(y1)
        bottom = page_height - float(y0)

    if x0 is None or x1 is None:
        raise ValueError("layout object bbox requires x0 and x1 coordinates")

    return _bbox_from_coordinates(
        x0=float(x0),
        top=float(top),
        x1=float(x1),
        bottom=float(bottom),
    )


def _bbox_from_coordinates(
    *,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
) -> tuple[BBox, list[str]]:
    warnings: list[str] = []
    if x1 <= x0:
        x1 = x0 + 0.01
        warnings.append("bbox_width_expanded_from_degenerate_pdf_geometry")
    if bottom <= top:
        bottom = top + 0.01
        warnings.append("bbox_height_expanded_from_degenerate_pdf_geometry")
    return (
        BBox(
            x0=x0,
            top=top,
            x1=x1,
            bottom=bottom,
            coordinate_system=PDF_POINT_COORDINATE_SYSTEM,
        ),
        warnings,
    )
