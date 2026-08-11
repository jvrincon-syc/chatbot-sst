from __future__ import annotations

import re

from chunking.application.child_chunk_builder import ChildChunkBuilder
from chunking.application.parent_chunk_builder import ParentChunkBuilder
from chunking.application.ports import TokenCounterPort
from chunking.domain.enums import StructuralBlockKind, ZeroOverlapReason
from chunking.domain.models import ChunkInvariantError, ChunkingProfile, ParentChunk, SourceSpan, StructuralBlock
from chunking.infrastructure.canonical_tokenizer import CanonicalTokenizer


def _span(
    *,
    page_start: int | None = 1,
    page_end: int | None = 1,
    char_start: int = 0,
    char_end: int = 0,
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
    heading_path: tuple[str, ...] = (),
    char_start: int = 0,
) -> StructuralBlock:
    return StructuralBlock.create(
        document_id="doc-child",
        ordinal=ordinal,
        kind=kind,
        text=text,
        source_span=_span(char_start=char_start, char_end=char_start + len(text)),
        heading_path=heading_path,
    )


def _profile() -> ChunkingProfile:
    return ChunkingProfile.local_structural_v1()


def _tokenizer() -> CanonicalTokenizer:
    return CanonicalTokenizer()


class _SeparatorSensitiveTokenizer(TokenCounterPort):
    def __init__(
        self,
        *,
        sentence_counts: dict[str, int],
        combined_counts: dict[str, int],
    ) -> None:
        self._sentence_counts = sentence_counts
        self._combined_counts = combined_counts

    def count_tokens(self, text: str) -> int:
        normalized = text.strip()
        if not normalized:
            return 0
        if normalized in self._combined_counts:
            return self._combined_counts[normalized]
        if normalized in self._sentence_counts:
            return self._sentence_counts[normalized]
        parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+|\n{2,}", normalized)
            if part.strip()
        ]
        if not parts:
            return 0
        return sum(self._sentence_counts[part] for part in parts)


def _sentence_with_token_target(target: int, *, index: int) -> str:
    tokenizer = _tokenizer()
    words = [f"token{index}_{value}" for value in range(max(4, target * 2))]
    current: list[str] = []
    for word in words:
        current.append(word)
        candidate = " ".join(current) + "."
        count = tokenizer.count_tokens(candidate)
        if count >= target:
            if count > target:
                current.pop()
                candidate = " ".join(current) + "."
            return candidate
    raise AssertionError(f"unable to build sentence for target {target}")


def _continuous_parent(*sentence_token_targets: int):
    sentences = [
        _sentence_with_token_target(target, index=index)
        for index, target in enumerate(sentence_token_targets, start=1)
    ]
    paragraph = " ".join(sentences)
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Procedimiento", heading_path=("Procedimiento",)),
        _block(
            1,
            StructuralBlockKind.PARAGRAPH,
            paragraph,
            heading_path=("Procedimiento",),
            char_start=20,
        ),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks, sentences


def _table_parent() -> tuple:
    long_value = " ".join(f"campo_{index}" for index in range(40))
    table = "\n".join(
        [
            "| Campo | Valor |",
            "| --- | --- |",
            f"| Codigo | {long_value} |",
            f"| Responsable | {long_value} |",
            f"| Plazo | {long_value} |",
            f"| Evidencia | {long_value} |",
            f"| Seguimiento | {long_value} |",
            f"| Hallazgo | {long_value} |",
        ]
    )
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Tabla de control", heading_path=("Tabla de control",)),
        _block(1, StructuralBlockKind.TABLE, table, heading_path=("Tabla de control",), char_start=20),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks


def _mixed_table_parent() -> tuple:
    article_76 = (
        "**ARTÍCULO 76.** Las faltas cometidas por los trabajadores en el desempeño "
        "de sus funciones laborales o en representación de la empresa se "
        "clasificarán en faltas leves y faltas muy graves."
    )
    intro = " ".join(
        [article_76, *[_sentence_with_token_target(40, index=index) for index in range(21, 29)]]
    )
    outro = " ".join(
        [
            "**ARTÍCULO 79.** Las sanciones para aplicar son las siguientes.",
            *[_sentence_with_token_target(38, index=index) for index in range(29, 35)],
        ]
    )
    table = "\n".join(
        [
            "<tr><th>TIPO</th><th>SANCIÓN</th></tr>",
            "<tr><td>A</td><td>Llamado de atención escrito</td></tr>",
            "<tr><td>B</td><td>Suspensión del trabajador hasta 3 días laborales.</td></tr>",
            "<tr><td>C</td><td>Suspensión del trabajador hasta 8 días laborales.</td></tr>",
            "</table>",
        ]
    )
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "CAPÍTULO XVIII", heading_path=("CAPÍTULO XVIII",)),
        _block(1, StructuralBlockKind.PARAGRAPH, intro, heading_path=("CAPÍTULO XVIII",), char_start=20),
        _block(
            2,
            StructuralBlockKind.TABLE,
            table,
            heading_path=("CAPÍTULO XVIII",),
            char_start=20 + len(intro) + 2,
        ),
        _block(
            3,
            StructuralBlockKind.PARAGRAPH,
            outro,
            heading_path=("CAPÍTULO XVIII",),
            char_start=20 + len(intro) + len(table) + 4,
        ),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks


def _form_parent() -> tuple:
    form = "\n".join(
        [
            "**Nombre:**",
            "**Documento:**",
            "**Cargo:**",
        ]
    )
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Formato", heading_path=("Formato",)),
        _block(1, StructuralBlockKind.FORM, form, heading_path=("Formato",), char_start=20),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks


def _list_parent() -> tuple:
    listing = "\n".join(
        [
            "1. Reportar incidente",
            "2. Informar al lider",
            "3. Registrar evidencia",
        ]
    )
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Pasos", heading_path=("Pasos",)),
        _block(1, StructuralBlockKind.LIST, listing, heading_path=("Pasos",), char_start=20),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks


def _long_list_parent() -> tuple:
    entries = [
        f"{index}. "
        + " ".join(
            [
                "La lista conserva evidencia documentada y trazabilidad completa."
                for _ in range(12)
            ]
        )
        for index in range(1, 9)
    ]
    listing = "\n".join(entries)
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Normas", heading_path=("Normas",)),
        _block(1, StructuralBlockKind.LIST, listing, heading_path=("Normas",), char_start=20),
    )
    parent = ParentChunkBuilder().build(
        document_id="doc-child",
        profile=_profile(),
        blocks=blocks,
    )[0]
    return parent, blocks


def test_aplica_overlap_cuando_parent_continuo_requiere_varios_children() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    assert children[0].overlap_next_tokens > 0
    assert children[1].overlap_previous_tokens == children[0].overlap_next_tokens


def test_calcula_overlap_nominal_del_12_por_ciento() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    second = children[1]
    assert abs(second.overlap_previous_tokens - round(second.token_count * 0.12)) <= 8


def test_limita_overlap_entre_30_y_60_tokens() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert all(
        30 <= child.overlap_previous_tokens <= 60
        for child in children[1:]
    )


def test_maximo_de_450_tokens_incluye_overlap() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert all(child.token_count <= 450 for child in children)


def test_overlap_repite_oraciones_completas() -> None:
    parent, blocks, sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    repeated_sentences = [
        sentence
        for sentence in sentences
        if sentence in children[0].text and sentence in children[1].text
    ]

    assert repeated_sentences
    assert children[1].text.startswith(repeated_sentences[0])


def test_primer_y_ultimo_child_tienen_bordes_correctos() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert ZeroOverlapReason.DOCUMENT_START in children[0].zero_overlap_reasons
    assert children[0].overlap_previous_tokens == 0
    assert children[-1].overlap_next_tokens == 0
    assert ZeroOverlapReason.SECTION_BOUNDARY in children[-1].zero_overlap_reasons


def test_token_start_y_token_end_siguen_offsets_reales_del_parent() -> None:
    parent, blocks, _sentences = _continuous_parent(*([38] * 16))
    tokenizer = _tokenizer()

    children = ChildChunkBuilder(tokenizer=tokenizer).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    for child in children:
        relative_start = child.source_span.char_start - parent.source_span.char_start
        relative_end = child.source_span.char_end - parent.source_span.char_start
        assert child.token_start == tokenizer.count_tokens(parent.text[:relative_start])
        assert child.token_end == tokenizer.count_tokens(parent.text[:relative_end])


def test_no_duplica_filas_de_tabla_por_overlap() -> None:
    parent, blocks = _table_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert all(child.overlap_previous_tokens == 0 for child in children)
    assert all(child.overlap_next_tokens == 0 for child in children)
    assert children[0].text.count("Codigo") == 1
    assert all("Campo" in child.context_prefix for child in children[1:])


def test_repite_header_de_tabla_como_contexto_no_como_overlap() -> None:
    parent, blocks = _table_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    assert children[1].context_prefix.startswith("| Campo | Valor |")
    assert children[1].overlap_previous_tokens == 0


def test_parent_mixto_con_tabla_no_descarta_texto_narrativo() -> None:
    parent, blocks = _mixed_table_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    assert any("faltas leves y faltas muy graves" in child.text for child in children)
    assert any("Llamado de atención escrito" in child.text for child in children)


def test_no_solapa_bloques_autocontenidos_de_formulario() -> None:
    parent, blocks = _form_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) == 1
    assert children[0].zero_overlap_reasons == frozenset(
        {
            ZeroOverlapReason.DOCUMENT_START,
            ZeroOverlapReason.SECTION_BOUNDARY,
            ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
        }
    )


def test_no_solapa_lista_autocontenida() -> None:
    parent, blocks = _list_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) == 1
    assert children[0].overlap_previous_tokens == 0
    assert children[0].overlap_next_tokens == 0


def test_lista_larga_no_se_trata_como_child_atomico() -> None:
    parent, blocks = _long_list_parent()

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    assert all(child.token_count <= _profile().child_max_tokens for child in children)


def test_no_solapa_parent_con_unico_child() -> None:
    parent, blocks, _sentences = _continuous_parent(80, 80)

    children = ChildChunkBuilder(tokenizer=_tokenizer()).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) == 1
    assert children[0].overlap_previous_tokens == 0
    assert children[0].overlap_next_tokens == 0


def test_mide_overlap_con_texto_combinado_real_antes_de_emitir_child() -> None:
    sentences = [
        "Frase alfa.",
        "Frase beta.",
        "Frase gamma.",
        "Frase delta.",
        "Frase epsilon.",
        "Frase zeta.",
        "Frase eta.",
        "Frase theta.",
        "Frase iota.",
        "Frase kappa.",
        "Frase lambda.",
    ]
    parent_text = " ".join(sentences)
    tokenizer = _SeparatorSensitiveTokenizer(
        sentence_counts={
            "Frase alfa.": 50,
            "Frase beta.": 50,
            "Frase gamma.": 50,
            "Frase delta.": 50,
            "Frase epsilon.": 50,
            "Frase zeta.": 30,
            "Frase eta.": 21,
            "Frase theta.": 21,
            "Frase iota.": 50,
            "Frase kappa.": 50,
            "Frase lambda.": 50,
        },
        combined_counts={
            "Frase eta. Frase theta.": 61,
        },
    )
    blocks = (
        _block(0, StructuralBlockKind.HEADING, "Procedimiento", heading_path=("Procedimiento",)),
        _block(
            1,
            StructuralBlockKind.PARAGRAPH,
            parent_text,
            heading_path=("Procedimiento",),
            char_start=20,
        ),
    )
    parent = ParentChunk.create(
        document_id="doc-child",
        profile_id=_profile().profile_id,
        ordinal=0,
        text=parent_text,
        source_span=_span(char_start=20, char_end=20 + len(parent_text)),
        block_ids=(blocks[1].block_id,),
    )

    children = ChildChunkBuilder(tokenizer=tokenizer).build(
        parent=parent,
        blocks=blocks,
        profile=_profile(),
    )

    assert len(children) > 1
    assert all(
        child.overlap_previous_tokens == 0 or 30 <= child.overlap_previous_tokens <= 60
        for child in children
    )
    assert all(
        child.overlap_next_tokens == 0 or 30 <= child.overlap_next_tokens <= 60
        for child in children
    )
