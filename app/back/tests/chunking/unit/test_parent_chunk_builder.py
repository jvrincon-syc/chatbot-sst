from __future__ import annotations

from chunking.application.parent_chunk_builder import ParentChunkBuilder
from chunking.domain.enums import StructuralBlockKind
from chunking.domain.models import ChunkingProfile, SourceSpan, StructuralBlock
from chunking.infrastructure.canonical_tokenizer import CanonicalTokenizer


def _span(
    *,
    page_start: int | None,
    page_end: int | None,
    char_start: int,
    char_end: int,
) -> SourceSpan:
    return SourceSpan(
        page_start=page_start,
        page_end=page_end,
        char_start=char_start,
        char_end=char_end,
    )


def _block(
    ordinal: int,
    kind: StructuralBlockKind,
    text: str,
    *,
    page_start: int | None = 1,
    page_end: int | None = 1,
    char_start: int = 0,
    char_end: int | None = None,
    heading_path: tuple[str, ...] = (),
) -> StructuralBlock:
    resolved_char_end = char_end if char_end is not None else char_start + len(text)
    return StructuralBlock.create(
        document_id="doc-parent",
        ordinal=ordinal,
        kind=kind,
        text=text,
        source_span=_span(
            page_start=page_start,
            page_end=page_end,
            char_start=char_start,
            char_end=resolved_char_end,
        ),
        heading_path=heading_path,
    )


def _profile() -> ChunkingProfile:
    return ChunkingProfile.local_structural_v1()


def test_crea_parent_semantico_cuando_seccion_atraviesa_paginas() -> None:
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Articulo 1", char_start=0, char_end=10, heading_path=("Articulo 1",)),
        _block(
            1,
            StructuralBlockKind.PARAGRAPH,
            "Texto que comienza en una pagina y termina en otra.",
            page_start=1,
            page_end=2,
            char_start=11,
            char_end=80,
            heading_path=("Articulo 1",),
        ),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert len(parents) == 1
    assert parents[0].source_span.page_start == 1
    assert parents[0].source_span.page_end == 2
    assert parents[0].block_ids == tuple(block.block_id for block in blocks)


def test_no_une_secciones_no_relacionadas_para_alcanzar_minimo() -> None:
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Articulo 1", heading_path=("Articulo 1",)),
        _block(1, StructuralBlockKind.PARAGRAPH, "Contenido corto A", char_start=20, heading_path=("Articulo 1",)),
        _block(2, StructuralBlockKind.HEADING, "Articulo 2", char_start=40, heading_path=("Articulo 2",)),
        _block(3, StructuralBlockKind.PARAGRAPH, "Contenido corto B", char_start=60, heading_path=("Articulo 2",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert len(parents) == 2
    assert all(len(parent.block_ids) == 2 for parent in parents)


def test_divide_seccion_larga_en_fronteras_de_bloque() -> None:
    long_a = " ".join(["control"] * 900)
    long_b = " ".join(["riesgo"] * 900)
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Procedimiento largo", heading_path=("Procedimiento largo",)),
        _block(1, StructuralBlockKind.PARAGRAPH, long_a, char_start=25, heading_path=("Procedimiento largo",)),
        _block(2, StructuralBlockKind.PARAGRAPH, long_b, char_start=25 + len(long_a) + 2, heading_path=("Procedimiento largo",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert len(parents) == 2
    assert parents[0].block_ids == (blocks[0].block_id, blocks[1].block_id)
    assert parents[1].block_ids == (blocks[2].block_id,)


def test_divide_seccion_larga_con_tokenizer_canonico() -> None:
    dense_numeric = " ".join(["1234567890"] * 600)
    assert CanonicalTokenizer().count_tokens(dense_numeric) > 1500
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Procedimiento numerico", heading_path=("Procedimiento numerico",)),
        _block(1, StructuralBlockKind.PARAGRAPH, dense_numeric, char_start=25, heading_path=("Procedimiento numerico",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert len(parents) == 2
    assert parents[0].block_ids == (blocks[0].block_id,)
    assert parents[1].block_ids == (blocks[1].block_id,)


def test_no_solapa_parents() -> None:
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Articulo 1", char_start=0, char_end=10, heading_path=("Articulo 1",)),
        _block(1, StructuralBlockKind.PARAGRAPH, "Contenido A", char_start=11, char_end=20, heading_path=("Articulo 1",)),
        _block(2, StructuralBlockKind.HEADING, "Articulo 2", char_start=21, char_end=30, heading_path=("Articulo 2",)),
        _block(3, StructuralBlockKind.PARAGRAPH, "Contenido B", char_start=31, char_end=40, heading_path=("Articulo 2",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert parents[0].source_span.char_end <= parents[1].source_span.char_start
    assert set(parents[0].block_ids).isdisjoint(parents[1].block_ids)


def test_cubre_todo_contenido_elegible() -> None:
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Procedimiento", heading_path=("Procedimiento",)),
        _block(1, StructuralBlockKind.PARAGRAPH, "Paso uno", char_start=20, heading_path=("Procedimiento",)),
        _block(2, StructuralBlockKind.LIST, "- A\n- B", char_start=40, heading_path=("Procedimiento",)),
        _block(3, StructuralBlockKind.TABLE, "| Campo | Valor |", char_start=60, heading_path=("Procedimiento",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    covered = {block_id for parent in parents for block_id in parent.block_ids}

    assert covered == {block.block_id for block in blocks}


def test_fusiona_heading_sin_cuerpo_con_siguiente_seccion() -> None:
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "ÍNDICE", heading_path=("ÍNDICE",)),
        _block(1, StructuralBlockKind.HEADING, "1. CAPÍTULO PRIMERO", heading_path=("1. CAPÍTULO PRIMERO",)),
        _block(2, StructuralBlockKind.PARAGRAPH, "Contenido real de la primera sección.", char_start=20, heading_path=("1. CAPÍTULO PRIMERO",)),
        _block(3, StructuralBlockKind.HEADING, "2. CAPÍTULO SEGUNDO", heading_path=("2. CAPÍTULO SEGUNDO",)),
        _block(4, StructuralBlockKind.PARAGRAPH, "Contenido real de la segunda sección.", char_start=60, heading_path=("2. CAPÍTULO SEGUNDO",)),
    )

    parents = ParentChunkBuilder().build(
        document_id="doc-parent",
        profile=_profile(),
        blocks=blocks,
    )

    assert len(parents) == 2
    assert parents[0].block_ids == (blocks[0].block_id, blocks[1].block_id, blocks[2].block_id)
    assert parents[1].block_ids == (blocks[3].block_id, blocks[4].block_id)
