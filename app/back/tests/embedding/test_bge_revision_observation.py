"""How the BGE model revision is observed, and what happens when it cannot be.

``model_revision`` is a semantic field: an unproven revision must block
verification instead of silently passing. These tests pin both branches.
"""

from __future__ import annotations

import pytest

from embedding.application.engine_registry import _bge_revision, _hub_snapshot_revision
from embedding.domain.models import UNKNOWN_REVISION


class _Config:
    def __init__(self, commit: str) -> None:
        self._commit_hash = commit


class _Inner:
    def __init__(self, commit: str) -> None:
        self.config = _Config(commit)


class _LoadedRuntime:
    def __init__(self, commit: str) -> None:
        self.model = _Inner(commit)


class _Provider:
    model_name = "BAAI/bge-m3"

    def __init__(self, model: object | None) -> None:
        self._model = model


def test_observa_la_revision_del_modelo_cargado() -> None:
    provider = _Provider(_LoadedRuntime("a" * 40))

    assert _bge_revision(provider) == "a" * 40


def test_devuelve_unknown_revision_cuando_no_puede_observarla(monkeypatch) -> None:
    monkeypatch.setattr(
        "embedding.application.engine_registry._hub_snapshot_revision",
        lambda _model_name: UNKNOWN_REVISION,
    )

    assert _bge_revision(_Provider(None)) == UNKNOWN_REVISION


def test_no_resuelve_revision_para_un_modelo_inexistente() -> None:
    pytest.importorskip("transformers")

    assert _hub_snapshot_revision("BAAI/modelo-que-no-existe-xyz") == UNKNOWN_REVISION


@pytest.mark.bge_runtime
def test_resuelve_el_commit_real_de_bge_m3_desde_la_cache() -> None:
    """Needs the BAAI/bge-m3 snapshot in the local Hugging Face cache."""

    pytest.importorskip("transformers")
    revision = _hub_snapshot_revision("BAAI/bge-m3")
    if revision == UNKNOWN_REVISION:
        pytest.skip("BAAI/bge-m3 is not present in the local Hugging Face cache")

    assert len(revision) == 40
    assert all(character in "0123456789abcdef" for character in revision)
