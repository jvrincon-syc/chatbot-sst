"""Perfil opt-in ``local-structural-v2``: propaga la sección a chunks sin mutar v1.

El contrato crítico es que ``local-structural-v1`` quede **byte-idéntico**
(mismo ``fingerprint`` de perfil y mismo ``chunk_id``): la mejora de sección es
opt-in por el flag ``include_section_context`` y nunca entra a la identidad de v1.
"""

from __future__ import annotations

from chunking.application.child_chunk_builder import ChildChunkBuilder
from chunking.application.parent_chunk_builder import ParentChunkBuilder
from chunking.domain.enums import StructuralBlockKind
from chunking.domain.models import (
    ChunkingProfile,
    ParentChunk,
    SourceSpan,
    StructuralBlock,
    _stable_id,
)
from chunking.infrastructure.canonical_tokenizer import CanonicalTokenizer


_HEADING_PATH = ("Titulo I", "Articulo 1")


def _span(char_start: int, char_end: int) -> SourceSpan:
    return SourceSpan(page_start=1, page_end=1, char_start=char_start, char_end=char_end)


def _block(
    ordinal: int,
    kind: StructuralBlockKind,
    text: str,
    *,
    char_start: int,
    heading_path: tuple[str, ...] = (),
) -> StructuralBlock:
    return StructuralBlock.create(
        document_id="doc-sec",
        ordinal=ordinal,
        kind=kind,
        text=text,
        source_span=_span(char_start, char_start + len(text)),
        heading_path=heading_path,
    )


def _blocks() -> tuple[StructuralBlock, ...]:
    return (
        _block(0, StructuralBlockKind.HEADING, "Articulo 1", char_start=0, heading_path=_HEADING_PATH),
        _block(
            1,
            StructuralBlockKind.PARAGRAPH,
            "Contenido breve de la seccion.",
            char_start=12,
            heading_path=_HEADING_PATH,
        ),
    )


# --- v1 byte-identidad -------------------------------------------------------


def test_fingerprint_de_perfil_v1_es_byte_identico_cuando_se_agrega_flag_de_seccion() -> None:
    profile = ChunkingProfile.local_structural_v1()
    # Reproduce la fórmula previa al campo: si alguien mete la clave nueva en el
    # payload de v1, este golden derivado rompe.
    expected = _stable_id(
        "chunking-profile",
        {
            "profile_id": "local-structural-v1",
            "child_min_tokens": 250,
            "child_target_tokens": 350,
            "child_max_tokens": 450,
            "overlap_ratio": 0.12,
            "overlap_min_tokens": 30,
            "overlap_max_tokens": 60,
            "zero_overlap_reasons": sorted(reason.value for reason in profile.zero_overlap_reasons),
        },
    )
    assert profile.include_section_context is False
    assert profile.fingerprint == expected


def test_chunk_id_v1_no_cambia_cuando_se_pasan_campos_de_seccion() -> None:
    span = _span(0, 20)
    without = ParentChunk.create(
        document_id="doc-sec",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=span,
        block_ids=("block-1",),
    )
    with_section = ParentChunk.create(
        document_id="doc-sec",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=span,
        block_ids=("block-1",),
        section_title="Articulo 1",
        section_path="Titulo I/Articulo 1",
    )
    # La sección está fuera del payload de identidad: mismo chunk_id.
    assert without.chunk_id == with_section.chunk_id


def test_parent_v1_no_propaga_seccion_y_payload_no_tiene_claves_de_seccion() -> None:
    parents = ParentChunkBuilder().build(
        document_id="doc-sec",
        profile=ChunkingProfile.local_structural_v1(),
        blocks=_blocks(),
    )
    parent = parents[0]
    assert parent.section_title is None
    assert parent.section_path is None
    payload = parent.as_payload()
    assert "section_title" not in payload
    assert "section_path" not in payload


def test_child_v1_conserva_context_prefix_vacio_y_payload_sin_seccion() -> None:
    profile = ChunkingProfile.local_structural_v1()
    blocks = _blocks()
    parent = ParentChunkBuilder().build(document_id="doc-sec", profile=profile, blocks=blocks)[0]
    children = ChildChunkBuilder(tokenizer=CanonicalTokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=profile,
    )
    assert children
    assert all(child.context_prefix == "" for child in children)
    assert all(child.section_title is None for child in children)
    assert all("section_title" not in child.as_payload() for child in children)


# --- v2 opt-in ---------------------------------------------------------------


def test_perfil_v2_activa_flag_y_difiere_del_fingerprint_de_v1() -> None:
    v2 = ChunkingProfile.local_structural_v2()
    assert v2.profile_id == "local-structural-v2"
    assert v2.include_section_context is True
    assert v2.fingerprint != ChunkingProfile.local_structural_v1().fingerprint


def test_parent_v2_puebla_section_title_y_section_path_desde_heading_path() -> None:
    parents = ParentChunkBuilder().build(
        document_id="doc-sec",
        profile=ChunkingProfile.local_structural_v2(),
        blocks=_blocks(),
    )
    parent = parents[0]
    assert parent.section_title == "Articulo 1"
    assert parent.section_path == "Titulo I/Articulo 1"
    payload = parent.as_payload()
    assert payload["section_title"] == "Articulo 1"
    assert payload["section_path"] == "Titulo I/Articulo 1"


def test_child_v2_hereda_seccion_y_antepone_heading_al_context_prefix() -> None:
    profile = ChunkingProfile.local_structural_v2()
    blocks = _blocks()
    parent = ParentChunkBuilder().build(document_id="doc-sec", profile=profile, blocks=blocks)[0]
    children = ChildChunkBuilder(tokenizer=CanonicalTokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=profile,
    )
    assert children
    assert all(child.section_title == "Articulo 1" for child in children)
    assert all(child.section_path == "Titulo I/Articulo 1" for child in children)
    # El heading encabeza el prefijo que luego se antepone al texto embebido.
    assert children[0].context_prefix == "Articulo 1"
    assert children[0].as_payload()["section_title"] == "Articulo 1"


def test_child_id_v2_difiere_de_v1_por_el_heading_en_context_prefix() -> None:
    blocks = _blocks()
    v1 = ChunkingProfile.local_structural_v1()
    v2 = ChunkingProfile.local_structural_v2()
    parent_v1 = ParentChunkBuilder().build(document_id="doc-sec", profile=v1, blocks=blocks)[0]
    parent_v2 = ParentChunkBuilder().build(document_id="doc-sec", profile=v2, blocks=blocks)[0]
    child_v1 = ChildChunkBuilder(tokenizer=CanonicalTokenizer()).build(
        parent=parent_v1, blocks=blocks, profile=v1
    )[0]
    child_v2 = ChildChunkBuilder(tokenizer=CanonicalTokenizer()).build(
        parent=parent_v2, blocks=blocks, profile=v2
    )[0]
    assert child_v1.chunk_id != child_v2.chunk_id
