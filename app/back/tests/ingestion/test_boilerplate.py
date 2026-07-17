from __future__ import annotations

from types import SimpleNamespace

from ingestion.layout.boilerplate import build_indexable_text, detect_boilerplate
from ingestion.schemas.common import BBox, PageBlock


def block(block_id: str, text: str, top: float, bottom: float, *, role: str | None = None) -> PageBlock:
    return PageBlock(
        block_id=block_id,
        text=text,
        bbox=BBox(x0=20, top=top, x1=560, bottom=bottom, coordinate_system="pdf_points"),
        extraction_method="pdf_digital",
        role=role,
    )


def page(page_number: int, blocks: list[PageBlock]) -> SimpleNamespace:
    return SimpleNamespace(page_number=page_number, width=612, height=792, blocks=blocks)


def test_consensus_boilerplate_removes_repeated_header_footer_only_from_indexable_text() -> None:
    pages = [
        page(1, [block("p1_h", "SYC Seguridad y Salud", 20, 38), block("p1_b", "Primer cuerpo", 150, 180), block("p1_f", "Pagina 1 de 2", 760, 775)]),
        page(2, [block("p2_h", "SYC Seguridad y Salud", 22, 40), block("p2_b", "Segundo cuerpo", 150, 180), block("p2_f", "Pagina 1 de 2", 758, 773)]),
    ]

    result = detect_boilerplate(pages)

    assert {match.region for match in result.matches} == {"header", "footer"}
    assert result.removed_spans_for_page(1)[0].text == "SYC Seguridad y Salud"
    assert pages[0].blocks[0].text == "SYC Seguridad y Salud"
    assert "SYC Seguridad y Salud" not in build_indexable_text(pages[0], result)
    assert "Primer cuerpo" in build_indexable_text(pages[0], result)


def test_boilerplate_requires_repetition_and_positional_agreement() -> None:
    pages = [
        page(1, [block("p1", "CONTROLADO", 20, 38), block("p1_body", "Texto uno", 100, 130)]),
        page(2, [block("p2", "CONTROLADO", 300, 318), block("p2_body", "Texto dos", 100, 130)]),
    ]

    result = detect_boilerplate(pages)

    assert result.matches == []
    assert "CONTROLADO" in build_indexable_text(pages[0], result)


def test_watermark_is_observed_without_destructive_removal() -> None:
    pages = [
        page(1, [block("wm1", "COPIA CONTROLADA", 350, 380, role="watermark"), block("body1", "Contenido", 100, 130)]),
        page(2, [block("wm2", "COPIA CONTROLADA", 352, 382, role="watermark"), block("body2", "Mas contenido", 100, 130)]),
    ]

    result = detect_boilerplate(pages)

    assert result.matches == []
    assert result.observations[0].status == "detected"
    assert "COPIA CONTROLADA" in build_indexable_text(pages[0], result)
