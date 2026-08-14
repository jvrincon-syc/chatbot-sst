"""Executable audit of the bundle-first and retrieval isolation invariants.

These are the claims the handoff makes about the official path. Codifying them
as tests means a future edit that breaks one fails CI instead of quietly
invalidating the documentation.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path("app/back/src")
BUNDLE_FIRST = SRC / "indexing/application/bundle_first"
FORBIDDEN_IN_INDEXING = (
    "EmbeddingFactory",
    "embed_documents",
    "resolve_document_engine",
    "resolve_query_engine",
    "StructureAwareNodeParser",
)


def _executable_source(path: Path) -> str:
    """Return module source with the docstring removed.

    The bundle-first modules name the forbidden symbols in prose precisely to
    say they are never called; only real code must be audited.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body = tree.body[1:]
    return ast.unparse(tree)


@pytest.mark.parametrize(
    "module",
    sorted(path.name for path in BUNDLE_FIRST.glob("*.py")),
)
def test_indexing_bundle_first_no_menciona_simbolos_de_embedding(module: str) -> None:
    source = _executable_source(BUNDLE_FIRST / module)

    for symbol in FORBIDDEN_IN_INDEXING:
        # Límite de identificador: un símbolo prohibido cuenta solo como identificador
        # completo (llamada/uso real), no como subcadena de otro nombre. Así
        # ``profile.can_embed_documents`` (flag de compatibilidad, no una operación de
        # embedding) no dispara un falso positivo sobre ``embed_documents``.
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])"
        assert not re.search(pattern, source), f"{module} references {symbol}"


def test_indexing_bundle_first_no_lee_document_profile() -> None:
    for path in BUNDLE_FIRST.glob("*.py"):
        assert "document.profile" not in _executable_source(path)


def test_indexing_bundle_first_no_importa_llama_index() -> None:
    for path in BUNDLE_FIRST.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("llama_index"), path.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("llama_index"), path.name


def test_solo_embedding_resuelve_motores_de_documento() -> None:
    callers: set[str] = set()
    for path in SRC.rglob("*.py"):
        if "resolve_document_engine" not in path.read_text(encoding="utf-8"):
            continue
        callers.add(path.relative_to(SRC).as_posix())

    # ports.py + engine_registry.py declare it; run_service and
    # profile_verification are the only callers, and all four live in Embedding.
    assert callers == {
        "embedding/application/ports.py",
        "embedding/application/engine_registry.py",
        "embedding/application/run_service.py",
        "embedding/application/profile_verification.py",
    }


def test_query_embedding_service_es_el_unico_caller_productivo() -> None:
    callers: list[str] = []
    for path in SRC.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if ".embed_queries(" in line:
                callers.append(f"{path.relative_to(SRC).as_posix()}")

    # engine_registry is the provider adapter; retrieval_service calls the
    # service, not an engine. Only QueryEmbeddingService touches an engine.
    assert set(callers) == {
        "embedding/application/engine_registry.py",
        "retrieval/application/query_embedding_service.py",
        "retrieval/application/retrieval_service.py",
    }
    engine_call = (
        SRC / "retrieval/application/query_embedding_service.py"
    ).read_text(encoding="utf-8")
    assert "engine.embed_queries(list(queries))" in engine_call

    service_call = (
        SRC / "retrieval/application/retrieval_service.py"
    ).read_text(encoding="utf-8")
    assert "self._query_embedding.embed_queries(" in service_call


def test_append_bundle_vectors_escribe_filas_inactivas() -> None:
    source = (
        SRC / "indexing/infrastructure/postgres/vector_repository.py"
    ).read_text(encoding="utf-8")
    append_body = source.split("def append_bundle_vectors")[1].split("def activate_bundle")[0]

    assert "is_active = false" in append_body
    assert "is_active = true" not in append_body


def test_el_mapping_lo_gobierna_embedding_bundle_chunks() -> None:
    source = (SRC / "indexing/application/bundle_first/index_bundle.py").read_text(
        encoding="utf-8"
    )

    assert "self._bundles.list_chunks(embedding_bundle_id)" in source
    assert "self._artifacts.load_vectors(" in source
    assert "vectors[chunk.vector_offset]" in source


def test_rollback_no_recalcula_embeddings() -> None:
    source = _executable_source(SRC / "indexing/application/bundle_first/activation.py")

    assert "rollback_to_bundle" in source
    for symbol in ("embed_documents", "embed_queries", "EmbeddingFactory"):
        assert symbol not in source
