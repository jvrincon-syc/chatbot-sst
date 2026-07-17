from __future__ import annotations

from types import SimpleNamespace

from ingestion.schemas.common import BBox, PageBlock
from ingestion.structure.forms import FormExtractor
from ingestion.structure.tables import TableExtractor


def box(x0: float, top: float, x1: float, bottom: float) -> BBox:
    return BBox(x0=x0, top=top, x1=x1, bottom=bottom, coordinate_system="pdf_points")


def test_table_extractor_preserves_matrix_rows_cells_and_observation() -> None:
    page = SimpleNamespace(
        page_number=7,
        tables=[
            {
                "bbox": box(20, 100, 580, 230),
                "rows": [
                    ["Factor", "AUMENTAN", "DISMINUYEN"],
                    ["Carga mental", "Ruido", "Pausas activas"],
                ],
                "cells": [
                    {"row_index": 0, "column_index": 0, "text": "Factor", "bbox": box(20, 100, 180, 130)},
                    {"row_index": 0, "column_index": 1, "text": "AUMENTAN", "bbox": box(180, 100, 380, 130)},
                    {"row_index": 0, "column_index": 2, "text": "DISMINUYEN", "bbox": box(380, 100, 580, 130)},
                    {"row_index": 1, "column_index": 0, "text": "Carga mental", "bbox": box(20, 130, 180, 160)},
                    {"row_index": 1, "column_index": 1, "text": "Ruido", "bbox": box(180, 130, 380, 160)},
                    {"row_index": 1, "column_index": 2, "text": "Pausas activas", "bbox": box(380, 130, 580, 160)},
                ],
            }
        ],
    )

    result = TableExtractor().evaluate(page)

    assert result.observation.status == "detected"
    assert result.tables[0].bbox == box(20, 100, 580, 230)
    assert result.tables[0].headers == ["Factor", "AUMENTAN", "DISMINUYEN"]
    assert result.tables[0].rows[1] == ["Carga mental", "Ruido", "Pausas activas"]
    assert "| Factor | AUMENTAN | DISMINUYEN |" in result.tables[0].markdown_representation
    assert result.tables[0].quality.kind == "unavailable"
    assert result.tables[0].quality.value is None


def test_table_extractor_rejects_boolean_quality_before_numeric_coercion() -> None:
    page = SimpleNamespace(
        page_number=3,
        tables=[
            {
                "rows": [["Campo", "Valor"]],
                "quality": True,
            }
        ],
    )

    result = TableExtractor().evaluate(page)

    assert result.tables[0].quality.kind == "unavailable"
    assert result.tables[0].quality.value is None


def test_table_extractor_distinguishes_not_detected_from_unavailable() -> None:
    empty_page = SimpleNamespace(page_number=1, tables=[])

    assert TableExtractor().evaluate(empty_page).observation.status == "not_detected"
    assert TableExtractor(backend_available=False).evaluate(empty_page).observation.status == "not_evaluated"


def test_form_extractor_preserves_complaint_labels_and_blank_response_regions() -> None:
    page = SimpleNamespace(
        page_number=2,
        blocks=[
            PageBlock(
                block_id="title",
                text="Formato de queja convivencia laboral",
                bbox=box(20, 30, 400, 50),
                extraction_method="pdf_digital",
                role="title",
            ),
            PageBlock(
                block_id="name_label",
                text="Nombre:",
                bbox=box(20, 100, 90, 118),
                extraction_method="pdf_digital",
                role="label",
            ),
            PageBlock(
                block_id="name_blank",
                text="",
                bbox=box(100, 108, 360, 110),
                extraction_method="pdf_digital",
                role="blank_area",
            ),
            PageBlock(
                block_id="desc_label",
                text="Descripcion:",
                bbox=box(20, 150, 120, 168),
                extraction_method="pdf_digital",
                role="label",
            ),
            PageBlock(
                block_id="desc_blank",
                text="",
                bbox=box(20, 175, 560, 240),
                extraction_method="pdf_digital",
                role="blank_area",
            ),
        ],
    )

    result = FormExtractor().evaluate(page)

    group = result.groups[0]
    assert result.observation.status == "detected"
    assert group.group_id == "complaint"
    assert [label.text for label in group.labels] == ["Nombre:", "Descripcion:"]
    assert group.controls[0].control_type == "blank_area"
    assert group.controls[0].label_id == "nombre"


def test_form_extractor_distinguishes_not_detected_from_unavailable() -> None:
    empty_page = SimpleNamespace(page_number=1, blocks=[])

    assert FormExtractor().evaluate(empty_page).observation.status == "not_detected"
    assert FormExtractor(backend_available=False).evaluate(empty_page).observation.status == "not_evaluated"
