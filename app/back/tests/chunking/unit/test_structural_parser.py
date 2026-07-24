from __future__ import annotations

import pytest

from chunking.application.structural_parser import StructuralParser
from chunking.domain.enums import StructuralBlockKind
from chunking.domain.models import NormalizedDocumentBundle, PageTrace, ValidatedSidecars


def _trace(
    *,
    page_number: int,
    char_start: int,
    char_end: int,
    text: str,
) -> PageTrace:
    return PageTrace(
        page_number=page_number,
        char_start=char_start,
        char_end=char_end,
        text_raw=text,
        text_normalized=text,
    )


def _bundle(
    markdown: str,
    *,
    page_traces: tuple[PageTrace, ...],
    sidecars: ValidatedSidecars | None = None,
) -> NormalizedDocumentBundle:
    return NormalizedDocumentBundle(
        document_id="doc-structural",
        source_hash="source-hash",
        corpus_version="corpus-v1",
        markdown=markdown,
        page_traces=page_traces,
        sidecars=sidecars or ValidatedSidecars(),
    )


def test_detecta_articulos_cuando_no_hay_headings() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "ARTICULO 1. Objeto\n\n"
        "Este procedimiento define controles.\n\n"
        "1.1 Alcance\n\n"
        "Aplica para todo el personal.\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
        )
    )

    assert [block.kind for block in blocks] == [
        StructuralBlockKind.HEADING,
        StructuralBlockKind.PARAGRAPH,
        StructuralBlockKind.HEADING,
        StructuralBlockKind.PARAGRAPH,
    ]
    assert blocks[0].text == "ARTICULO 1. Objeto"
    assert blocks[2].text == "1.1 Alcance"


def test_detecta_numeral_como_heading_despues_de_texto_corrido() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "Contexto introductorio.\n"
        "1.1 Alcance\n\n"
        "Aplica para todo el personal.\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
        )
    )

    assert [block.kind for block in blocks] == [
        StructuralBlockKind.PARAGRAPH,
        StructuralBlockKind.HEADING,
        StructuralBlockKind.PARAGRAPH,
    ]


def test_ignora_heading_repetido_como_frontera_semantica() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "## SYC\n\n"
        "Texto principal de la primera pagina.\n\n"
        "<!-- page: 2 -->\n"
        "## SYC\n\n"
        "Texto principal de la segunda pagina.\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(
                _trace(page_number=1, char_start=0, char_end=66, text="## SYC\nTexto principal de la primera pagina."),
                _trace(
                    page_number=2,
                    char_start=66,
                    char_end=len(markdown),
                    text="## SYC\nTexto principal de la segunda pagina.",
                ),
            ),
        )
    )

    assert [block.kind for block in blocks] == [
        StructuralBlockKind.NOTE,
        StructuralBlockKind.PARAGRAPH,
        StructuralBlockKind.NOTE,
        StructuralBlockKind.PARAGRAPH,
    ]
    assert all(block.heading_path == () for block in blocks)


def test_agrupa_lista_cuando_items_son_continuos() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "- Reportar incidente\n"
        "- Informar al lider\n"
        "- Registrar evidencia\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind is StructuralBlockKind.LIST
    assert blocks[0].text.count("\n") == 2


def test_agrupa_lista_numerada_como_list_y_no_como_heading() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "1. Reportar incidente\n"
        "2. Informar al lider\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind is StructuralBlockKind.LIST


def test_preserva_tabla_como_bloque_estructural() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "| Campo | Valor |\n"
        "| --- | --- |\n"
        "| Codigo | SST-01 |\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
            sidecars=ValidatedSidecars(
                tables_present=True,
                table_markdown=("| Campo | Valor |\n| --- | --- |\n| Codigo | SST-01 |",),
            ),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind is StructuralBlockKind.TABLE
    assert "Codigo" in blocks[0].text


def test_preserva_formulario_como_bloque_estructural() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "# Formato de Reporte\n\n"
        "**Nombre:**\n"
        "**Documento:**\n"
        "**Cargo:**\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
            sidecars=ValidatedSidecars(
                forms_present=True,
                form_titles=("Formato de Reporte",),
            ),
        )
    )

    assert [block.kind for block in blocks] == [
        StructuralBlockKind.HEADING,
        StructuralBlockKind.FORM,
    ]
    assert "Nombre" in blocks[1].text


def test_no_crea_parent_por_cambio_de_pagina() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "El procedimiento continua en la siguiente pagina sin cerrar la idea "
        "porque necesita el mismo contexto.\n"
        "<!-- page: 2 -->\n"
        "La misma idea sigue aca sin nuevo titulo.\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(
                _trace(
                    page_number=1,
                    char_start=0,
                    char_end=126,
                    text="El procedimiento continua en la siguiente pagina sin cerrar la idea porque necesita el mismo contexto.",
                ),
                _trace(
                    page_number=2,
                    char_start=126,
                    char_end=len(markdown),
                    text="La misma idea sigue aca sin nuevo titulo.",
                ),
            ),
        )
    )

    assert len(blocks) == 1
    assert blocks[0].kind is StructuralBlockKind.PARAGRAPH
    assert blocks[0].source_span.page_start == 1
    assert blocks[0].source_span.page_end == 2


def test_conserva_heading_legitimo_repetido_fuera_del_borde_de_pagina() -> None:
    markdown = (
        "<!-- page: 1 -->\n"
        "Introduccion previa.\n\n"
        "## Responsables\n\n"
        "Contenido del primer bloque.\n\n"
        "Texto puente.\n\n"
        "## Responsables\n\n"
        "Contenido del segundo bloque.\n"
    )
    parser = StructuralParser()

    blocks = parser.parse(
        _bundle(
            markdown,
            page_traces=(_trace(page_number=1, char_start=0, char_end=len(markdown), text=markdown),),
        )
    )

    heading_blocks = [block for block in blocks if block.text == "Responsables"]

    assert len(heading_blocks) == 2
    assert all(block.kind is StructuralBlockKind.HEADING for block in heading_blocks)


def test_falla_cerrado_cuando_una_region_no_tiene_page_trace() -> None:
    markdown = "<!-- page: 1 -->\nContenido sin trazabilidad.\n"
    parser = StructuralParser()

    with pytest.raises(ValueError, match="PAGE_TRACE_UNRESOLVED"):
        parser.parse(
            _bundle(
                markdown,
                page_traces=(),
            )
        )
