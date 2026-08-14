"""``build_nodes`` propaga ``section_title``/``section_path`` desde el bundle.

Con un bundle v2 (sección presente) los nodos parent y child llevan la sección;
con un bundle v1 (sección ausente) los campos quedan None: build_nodes nunca
inventa la sección que el chunk no trae.
"""

from __future__ import annotations

from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    ChunkBundleContent,
    SourceChildChunk,
    SourceParentChunk,
    SourceSpanRecord,
)
from indexing.application.bundle_first.index_bundle import build_nodes


_PROJECT = "proj_alpha"
_BUNDLE = "cb_doc01"


def _content(*, section_title: str | None, section_path: str | None) -> ChunkBundleContent:
    span = SourceSpanRecord(char_start=0, char_end=4)
    return ChunkBundleContent(
        parents=(
            SourceParentChunk(
                chunk_id="p1",
                document_id="doc01",
                profile_id="local-structural-v2",
                ordinal=0,
                text="parent",
                source_span=span,
                block_ids=["b1"],
                section_title=section_title,
                section_path=section_path,
            ),
        ),
        children=(
            SourceChildChunk(
                chunk_id="c1",
                parent_id="p1",
                document_id="doc01",
                profile_id="local-structural-v2",
                ordinal=0,
                text="child",
                source_span=span,
                token_count=1,
                section_title=section_title,
                section_path=section_path,
            ),
        ),
        source_content_fingerprint="f" * 64,
        corpus_version="corpus-1",
        document_id="doc01",
        source_relpath="a/doc01.pdf",
        source_hash="a" * 64,
        normalized_relpath="a/doc01.md",
    )


def _nodes(content: ChunkBundleContent):
    return build_nodes(
        content=content,
        chunk_bundle_id=_BUNDLE,
        chunking_bundle_fingerprint="f" * 64,
        chunking_version="local-structural-v2",
        ingestion_origin="local",
        project_id=_PROJECT,
    )


def test_build_nodes_propaga_seccion_cuando_el_bundle_v2_la_trae() -> None:
    nodes = _nodes(_content(section_title="Articulo 1", section_path="Titulo I/Articulo 1"))
    parent = next(node for node in nodes if node.node_role == "parent")
    child = next(node for node in nodes if node.node_role == "child")

    assert parent.section_title == "Articulo 1"
    assert parent.section_path == "Titulo I/Articulo 1"
    assert child.section_title == "Articulo 1"
    assert child.section_path == "Titulo I/Articulo 1"


def test_build_nodes_deja_seccion_en_none_cuando_el_bundle_es_v1() -> None:
    nodes = _nodes(_content(section_title=None, section_path=None))

    assert all(node.section_title is None for node in nodes)
    assert all(node.section_path is None for node in nodes)
