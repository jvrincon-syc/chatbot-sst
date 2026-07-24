from __future__ import annotations

from dataclasses import replace

import pytest

from chunking.domain.enums import StructuralBlockKind, ZeroOverlapReason
from chunking.domain.errors import ChunkInvariantError, ChunkingProfileError
from chunking.domain.models import (
    ChildChunk,
    ChunkBundle,
    ChunkingProfile,
    ChunkingRun,
    NormalizedDocumentBundle,
    OverlapSpan,
    ParentChunk,
    SourceSpan,
    StructuralBlock,
)
from chunking.domain.policies import ZeroOverlapPolicy


def _profile(**changes: object) -> ChunkingProfile:
    values: dict[str, object] = {
        "profile_id": "local-structural-v1",
        "child_min_tokens": 250,
        "child_target_tokens": 350,
        "child_max_tokens": 450,
        "overlap_ratio": 0.12,
        "overlap_min_tokens": 30,
        "overlap_max_tokens": 60,
        "zero_overlap_reasons": frozenset(
            {
                ZeroOverlapReason.DOCUMENT_START,
                ZeroOverlapReason.SECTION_BOUNDARY,
                ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY,
            }
        ),
    }
    values.update(changes)
    return ChunkingProfile(**values)


def _span(**changes: object) -> SourceSpan:
    values: dict[str, object] = {
        "page_start": 1,
        "page_end": 1,
        "char_start": 0,
        "char_end": 18,
    }
    values.update(changes)
    return SourceSpan(**values)


def _parent() -> ParentChunk:
    return ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )


def _child(**changes: object) -> ChildChunk:
    values: dict[str, object] = {
        "document_id": "doc-1",
        "profile_id": "local-structural-v1",
        "parent_id": _parent().chunk_id,
        "ordinal": 0,
        "text": "Procedimiento seguro",
        "source_span": _span(),
        "token_start": 0,
        "token_end": 3,
        "token_count": 3,
        "overlap_previous_tokens": 0,
        "overlap_next_tokens": 0,
        "zero_overlap_reasons": frozenset(
            {
                ZeroOverlapReason.DOCUMENT_START,
                ZeroOverlapReason.SECTION_BOUNDARY,
            }
        ),
    }
    values.update(changes)
    return ChildChunk.create(**values)


def _document_with_parent() -> tuple[NormalizedDocumentBundle, ParentChunk]:
    block = StructuralBlock.create(
        document_id="doc-1",
        ordinal=0,
        kind=StructuralBlockKind.PARAGRAPH,
        text="Procedimiento seguro",
        source_span=_span(),
    )
    document = NormalizedDocumentBundle(
        document_id="doc-1",
        source_hash="source-hash",
        corpus_version="corpus-v1",
        markdown="Procedimiento seguro",
        structural_blocks=(block,),
    )
    parent = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=(block.block_id,),
    )
    return document, parent


def _overlapped_child(parent: ParentChunk, **changes: object) -> ChildChunk:
    values: dict[str, object] = {
        "document_id": "doc-1",
        "profile_id": "local-structural-v1",
        "parent_id": parent.chunk_id,
        "ordinal": 0,
        "text": "Procedimiento seguro",
        "source_span": _span(),
        "token_start": 0,
        "token_end": 100,
        "token_count": 100,
        "overlap_previous_tokens": 30,
        "overlap_next_tokens": 0,
        "overlap_previous_span": OverlapSpan(token_start=0, token_end=30),
        "zero_overlap_reasons": frozenset({ZeroOverlapReason.SECTION_BOUNDARY}),
    }
    values.update(changes)
    return ChildChunk.create(**values)


def test_rechaza_child_cuando_parent_no_existe() -> None:
    child = _child(parent_id="missing-parent")

    with pytest.raises(ChunkInvariantError, match="parent"):
        ChunkBundle(
            document_id="doc-1",
            profile=_profile(),
            parents=(_parent(),),
            children=(child,),
        )


def test_rechaza_overlap_cuando_supera_el_child() -> None:
    with pytest.raises(ChunkInvariantError, match="overlap"):
        _child(overlap_previous_tokens=4, token_count=3, zero_overlap_reasons=frozenset())


def test_rechaza_child_cuyo_total_incluido_overlap_supera_el_maximo() -> None:
    profile = _profile()
    child = _child(token_count=451)

    with pytest.raises(ChunkInvariantError, match="child_max_tokens"):
        ChunkBundle(
            document_id="doc-1",
            profile=profile,
            parents=(_parent(),),
            children=(child,),
        )


def test_rechaza_perfil_cuando_minimo_objetivo_y_maximo_son_incoherentes() -> None:
    with pytest.raises(ChunkingProfileError, match="child_min_tokens"):
        _profile(child_min_tokens=351)


def test_rechaza_perfil_cuando_limites_de_overlap_son_incoherentes() -> None:
    with pytest.raises(ChunkingProfileError, match="overlap_min_tokens"):
        _profile(overlap_min_tokens=61)


def test_perfil_local_define_ratio_y_limites_de_overlap() -> None:
    profile = ChunkingProfile.local_structural_v1()

    assert profile.profile_id == "local-structural-v1"
    assert profile.child_min_tokens == 250
    assert profile.child_target_tokens == 350
    assert profile.child_max_tokens == 450
    assert profile.overlap_ratio == 0.12
    assert profile.overlap_min_tokens == 30
    assert profile.overlap_max_tokens == 60
    assert profile.overlap_tokens_for_target() == 42


def test_rechaza_page_range_cuando_end_es_menor() -> None:
    with pytest.raises(ChunkInvariantError, match="page_end"):
        _span(page_start=2, page_end=1)


def test_permite_page_range_desconocido_pero_rechaza_null_parcial() -> None:
    span = _span(page_start=None, page_end=None)

    assert span.page_start is None
    assert span.page_end is None
    assert span.as_payload()["page_start"] is None
    assert span.as_payload()["page_end"] is None

    with pytest.raises(ChunkInvariantError, match="page_start and page_end"):
        _span(page_start=None, page_end=1)


def test_rechaza_rangos_negativos_y_chunks_vacios() -> None:
    with pytest.raises(ChunkInvariantError, match="char_start"):
        _span(char_start=-1)

    with pytest.raises(ChunkInvariantError, match="text"):
        StructuralBlock.create(
            document_id="doc-1",
            ordinal=0,
            kind=StructuralBlockKind.PARAGRAPH,
            text="   ",
            source_span=_span(),
        )

    with pytest.raises(ChunkInvariantError, match="text"):
        ParentChunk(
            chunk_id="parent-manual",
            document_id="doc-1",
            profile_id="local-structural-v1",
            ordinal=0,
            text=" ",
            source_span=_span(),
            block_ids=("block-1",),
        )


def test_rechaza_overlap_cero_sin_excepcion_semantica_permitida() -> None:
    with pytest.raises(ChunkInvariantError, match="zero_overlap_reasons"):
        _child(zero_overlap_reasons=frozenset())

    restricted_profile = _profile(
        zero_overlap_reasons=frozenset({ZeroOverlapReason.TABLE_OR_FORM_BOUNDARY})
    )
    with pytest.raises(ChunkInvariantError, match="not allowed"):
        ChunkBundle(
            document_id="doc-1",
            profile=restricted_profile,
            parents=(_parent(),),
            children=(_child(),),
        )


def test_genera_ids_iguales_cuando_entrada_y_perfil_no_cambian() -> None:
    first = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )
    second = ParentChunk.create(
        document_id="doc-1",
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("block-1",),
    )

    assert first.chunk_id == second.chunk_id
    assert first.chunk_id.startswith("parent-")


def test_rechaza_id_que_no_corresponde_al_contenido_y_posicion() -> None:
    with pytest.raises(ChunkInvariantError, match="chunk_id"):
        ParentChunk(
            chunk_id="parent-injected",
            document_id="doc-1",
            profile_id="local-structural-v1",
            ordinal=0,
            text="Procedimiento seguro",
            source_span=_span(),
            block_ids=("block-1",),
        )


def test_cambia_fingerprint_cuando_cambia_overlap() -> None:
    base = _profile()
    changed = _profile(overlap_ratio=0.10)

    assert base.fingerprint != changed.fingerprint


def test_cambia_fingerprint_de_bundle_y_run_cuando_cambia_el_solapamiento() -> None:
    document, parent = _document_with_parent()
    first = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(_overlapped_child(parent),),
    )
    second = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(
            _overlapped_child(
                parent,
                token_count=101,
                overlap_previous_tokens=31,
                overlap_previous_span=OverlapSpan(token_start=0, token_end=31),
            ),
        ),
    )

    assert first.children[0].chunk_id == second.children[0].chunk_id
    assert first.fingerprint != second.fingerprint
    assert ChunkingRun.create(document=document, bundle=first).run_id != ChunkingRun.create(
        document=document,
        bundle=second,
    ).run_id


def test_rechaza_chunking_run_cuando_parent_apunta_a_block_id_inexistente() -> None:
    document, _ = _document_with_parent()
    parent = ParentChunk.create(
        document_id=document.document_id,
        profile_id="local-structural-v1",
        ordinal=0,
        text="Procedimiento seguro",
        source_span=_span(),
        block_ids=("missing-block",),
    )
    bundle = ChunkBundle(
        document_id=document.document_id,
        profile=_profile(),
        parents=(parent,),
        children=(_overlapped_child(parent),),
    )

    with pytest.raises(ChunkInvariantError, match="parent block_ids"):
        ChunkingRun.create(document=document, bundle=bundle)


def test_rechaza_valores_de_enum_invalidos_en_runtime() -> None:
    with pytest.raises(ChunkInvariantError, match="kind"):
        StructuralBlock.create(
            document_id="doc-1",
            ordinal=0,
            kind="paragraph",  # type: ignore[arg-type]
            text="Procedimiento seguro",
            source_span=_span(),
        )

    with pytest.raises(ChunkingProfileError, match="zero_overlap_reasons"):
        _profile(zero_overlap_reasons=frozenset({"not-a-reason"}))

    with pytest.raises(ChunkInvariantError, match="allowed_reasons"):
        ZeroOverlapPolicy(frozenset({"not-a-reason"}))


def test_rechaza_zero_overlap_reason_invalido_al_construir_child() -> None:
    with pytest.raises(ChunkInvariantError, match="zero_overlap_reasons"):
        _child(zero_overlap_reasons=frozenset({"not-a-reason"}))

    with pytest.raises(ChunkInvariantError, match="zero_overlap_reasons"):
        replace(_child(), zero_overlap_reasons=frozenset({"not-a-reason"}))
