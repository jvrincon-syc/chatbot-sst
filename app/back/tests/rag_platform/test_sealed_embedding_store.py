"""Fase 4: los embedding bundles sellados son inmutables y content-addressed.

Espeja las garantías de ``SealedChunkStore`` (ADR-007 §4): sellar es idempotente
cuando el contenido coincide, falla cerrado cuando difiere, y valida el contrato
ANTES de promover (lección de la revisión de Fase 3): una entrada inválida no deja
ningún archivo sellado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_platform.domain.errors import SealedBundleConflict
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import SealingStatus
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver
from rag_platform.infrastructure.storage.sealed_embedding_store import (
    SealedEmbeddingStore,
)


_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_sst-general")
_BUNDLE_ID = "eb_release001_doc01"
_MANIFEST = {"schema_version": "sealed-embedding-v1", "vector_count": 2}
_VECTORS = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
_CHUNK_MAP = [
    {"child_chunk_id": "c1", "vector_offset": 0},
    {"child_chunk_id": "c2", "vector_offset": 1},
]


def _store(tmp_path: Path) -> SealedEmbeddingStore:
    return SealedEmbeddingStore(ProjectStorageResolver(tmp_path))


def _seal(store: SealedEmbeddingStore, **overrides: object):
    payload: dict[str, object] = {
        "project_id": _PROJECT,
        "embedding_bundle_id": _BUNDLE_ID,
        "source_chunk_bundle_id": "cb_doc01",
        "dimension": 3,
        "distance_metric": "cosine",
        "manifest": _MANIFEST,
        "vectors": _VECTORS,
        "chunk_map": _CHUNK_MAP,
    }
    payload.update(overrides)
    return store.stage_and_seal(**payload)  # type: ignore[arg-type]


def _bundle_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "sst-general" / "embeddings" / _BUNDLE_ID


def test_sella_embedding_content_addressed_cuando_es_nuevo(tmp_path: Path) -> None:
    store = _store(tmp_path)

    sealed = _seal(store)

    assert sealed.sealing_status is SealingStatus.SEALED
    assert sealed.bundle_dir_relpath == f"embeddings/{_BUNDLE_ID}"
    assert sealed.dimension == 3
    assert sealed.vector_count == 2
    bundle_dir = _bundle_dir(tmp_path)
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "vectors.jsonl").exists()
    assert (bundle_dir / "chunk_map.jsonl").exists()
    assert (bundle_dir / "checksums.json").exists()
    assert set(sealed.checksums) == {"manifest.json", "vectors.jsonl", "chunk_map.jsonl"}


def test_resellar_es_idempotente_cuando_el_contenido_coincide(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _seal(store)
    bundle_dir = _bundle_dir(tmp_path)
    before = {c.name: c.read_bytes() for c in sorted(bundle_dir.iterdir())}

    second = _seal(store)

    after = {c.name: c.read_bytes() for c in sorted(bundle_dir.iterdir())}
    assert second.checksums == first.checksums
    assert after == before


def test_no_sobreescribe_cuando_el_contenido_difiere(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _seal(store)
    bundle_dir = _bundle_dir(tmp_path)
    before = {c.name: c.read_bytes() for c in sorted(bundle_dir.iterdir())}

    with pytest.raises(SealedBundleConflict):
        _seal(store, vectors=[[9.9, 9.9, 9.9], [0.4, 0.5, 0.6]])

    after = {c.name: c.read_bytes() for c in sorted(bundle_dir.iterdir())}
    assert after == before


def test_entrada_invalida_no_deja_embedding_sellado(tmp_path: Path) -> None:
    # Fail-closed: un vector con dimensión errónea se rechaza ANTES de promover; no
    # debe quedar checksums.json (marker de commit) ni manifest sellado.
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        _seal(store, vectors=[[0.1, 0.2], [0.4, 0.5, 0.6]])

    bundle_dir = _bundle_dir(tmp_path)
    assert not (bundle_dir / "checksums.json").exists()
    assert not (bundle_dir / "manifest.json").exists()


def test_verify_checksum_detecta_alteracion(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sealed = _seal(store)

    assert store.verify_checksum(
        project_id=_PROJECT,
        embedding_bundle_id=_BUNDLE_ID,
        expected=dict(sealed.checksums),
    )

    tampered = dict(sealed.checksums)
    tampered["vectors.jsonl"] = "0" * 64
    assert not store.verify_checksum(
        project_id=_PROJECT,
        embedding_bundle_id=_BUNDLE_ID,
        expected=tampered,
    )
