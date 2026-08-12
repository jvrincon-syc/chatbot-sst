"""Fase 4: identidad física de nodos namespaced por proyecto (ADR-007 §2).

``physical_node_id`` aísla nodos entre proyectos: dos proyectos con el mismo
``source_chunk_id`` obtienen ``node_id`` distinto. La expansión parent→child usa el
``parent_node_id`` físico, no el ``source_parent_chunk_id`` (evidencia). El
namespacing es **gated**: sin ``project_id`` la lane legacy conserva
``node_id == source_chunk_id`` byte-idéntico.
"""

from __future__ import annotations

from embedding.infrastructure.filesystem.chunk_bundle_reader import (
    ChunkBundleContent,
    SourceChildChunk,
    SourceParentChunk,
    SourceSpanRecord,
)
from indexing.application.bundle_first.index_bundle import build_nodes
from rag_platform.domain.identity import IdentityKind, PlatformId, physical_node_id
from rag_platform.domain.models import PhysicalNode


_PROJECT_A = "proj_alpha"
_PROJECT_B = "proj_beta"
_BUNDLE = "cb_doc01"


def _content() -> ChunkBundleContent:
    span = SourceSpanRecord(char_start=0, char_end=4)
    return ChunkBundleContent(
        parents=(
            SourceParentChunk(
                chunk_id="p1",
                document_id="doc01",
                profile_id="cp_v1",
                ordinal=0,
                text="parent",
                source_span=span,
                block_ids=["b1"],
            ),
        ),
        children=(
            SourceChildChunk(
                chunk_id="c1",
                parent_id="p1",
                document_id="doc01",
                profile_id="cp_v1",
                ordinal=0,
                text="child",
                source_span=span,
                token_count=1,
            ),
        ),
        source_content_fingerprint="f" * 64,
        corpus_version="corpus-legacy",
        document_id="doc01",
        source_relpath="a/doc01.pdf",
        source_hash="a" * 64,
        normalized_relpath="a/doc01.md",
    )


def test_physical_node_id_namespaced_por_proyecto() -> None:
    same_project = physical_node_id(
        project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="c1"
    )
    same_project_again = physical_node_id(
        project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="c1"
    )
    other_project = physical_node_id(
        project_id=_PROJECT_B, source_chunk_bundle_id=_BUNDLE, source_chunk_id="c1"
    )

    assert same_project == same_project_again  # determinista
    assert same_project.startswith("pnode_")
    assert same_project != other_project  # aislado por proyecto
    assert same_project != "c1"  # separado de la evidencia


def test_parent_expansion_uses_physical_parent_node_id() -> None:
    parent_a = physical_node_id(
        project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="p1"
    )
    child_a = PhysicalNode(
        project_id=PlatformId(IdentityKind.PROJECT, _PROJECT_A),
        node_id=physical_node_id(
            project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="c1"
        ),
        source_chunk_bundle_id=_BUNDLE,
        source_chunk_id="c1",
        node_role="child",
        parent_node_id=parent_a,
        source_parent_chunk_id="p1",
    )

    # La expansión usa el parent físico, no el source_parent_chunk_id (evidencia).
    assert child_a.parent_node_id == parent_a
    assert child_a.parent_node_id != child_a.source_parent_chunk_id

    parent_b = physical_node_id(
        project_id=_PROJECT_B, source_chunk_bundle_id=_BUNDLE, source_chunk_id="p1"
    )
    # Mismo source_parent_chunk_id "p1" en dos proyectos => parent físico distinto.
    assert parent_a != parent_b


def test_build_nodes_exige_project_id_pure_platform() -> None:
    # ADR-008: la lane legacy fue retirada; build_nodes ya no acepta llamadas sin
    # project_id (antes producía node_id == source_chunk_id byte-idéntico).
    import pytest

    with pytest.raises(TypeError):
        build_nodes(
            content=_content(),
            chunk_bundle_id=_BUNDLE,
            chunking_bundle_fingerprint="f" * 64,
            chunking_version="cp_v1",
            ingestion_origin="local",
        )


def test_build_nodes_plataforma_namespaced_cuando_hay_proyecto() -> None:
    nodes = build_nodes(
        content=_content(),
        chunk_bundle_id=_BUNDLE,
        chunking_bundle_fingerprint="f" * 64,
        chunking_version="cp_v1",
        ingestion_origin="local",
        project_id=_PROJECT_A,
    )

    parent = next(node for node in nodes if node.node_role == "parent")
    child = next(node for node in nodes if node.node_role == "child")

    expected_parent = physical_node_id(
        project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="p1"
    )
    expected_child = physical_node_id(
        project_id=_PROJECT_A, source_chunk_bundle_id=_BUNDLE, source_chunk_id="c1"
    )
    assert parent.node_id == expected_parent
    assert child.node_id == expected_child
    # Padre de expansión físico, evidencia conservada aparte.
    assert child.parent_node_id == expected_parent
    assert child.source_parent_chunk_id == "p1"
    assert child.source_chunk_id == "c1"
    assert child.parent_node_id != child.source_parent_chunk_id


def test_build_nodes_dos_proyectos_mismo_chunk_no_colisionan() -> None:
    nodes_a = build_nodes(
        content=_content(),
        chunk_bundle_id=_BUNDLE,
        chunking_bundle_fingerprint="f" * 64,
        chunking_version="cp_v1",
        ingestion_origin="local",
        project_id=_PROJECT_A,
    )
    nodes_b = build_nodes(
        content=_content(),
        chunk_bundle_id=_BUNDLE,
        chunking_bundle_fingerprint="f" * 64,
        chunking_version="cp_v1",
        ingestion_origin="local",
        project_id=_PROJECT_B,
    )

    ids_a = {node.node_id for node in nodes_a}
    ids_b = {node.node_id for node in nodes_b}
    assert ids_a.isdisjoint(ids_b)
