"""Fase 3: los chunk bundles sellados son inmutables y append-only.

Un bundle sellado referenciado por una release no cambia de ruta, hash ni
contenido. Sellar es idempotente cuando el contenido coincide y falla cerrado
cuando difiere; nunca sobreescribe archivos ya sellados (invariante §3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_platform.domain.errors import SealedBundleConflict
from rag_platform.domain.identity import IdentityKind, PlatformId
from rag_platform.domain.models import SealingStatus
from rag_platform.infrastructure.storage.project_storage import ProjectStorageResolver
from rag_platform.infrastructure.storage.sealed_chunk_store import SealedChunkStore


_PROJECT = PlatformId(IdentityKind.PROJECT, "proj_sst-general")
_FINGERPRINT = "a" * 64
_BUNDLE_ID = "cb_release001_doc01"
_MANIFEST = {"schema_version": "sealed-v1", "parent_count": 1, "child_count": 1}
_PARENTS = [{"chunk_id": "p1", "ordinal": 0, "text": "parent"}]
_CHILDREN = [{"chunk_id": "c1", "parent_id": "p1", "ordinal": 0, "text": "child"}]


def _store(tmp_path: Path) -> SealedChunkStore:
    return SealedChunkStore(ProjectStorageResolver(tmp_path))


def _seal(store: SealedChunkStore, **overrides: object):
    payload = {
        "project_id": _PROJECT,
        "chunk_bundle_id": _BUNDLE_ID,
        "normalized_document_id": "ndoc_01",
        "chunking_profile_fingerprint": _FINGERPRINT,
        "bundle_schema_version": "sealed-v1",
        "manifest": _MANIFEST,
        "parent_chunks": _PARENTS,
        "child_chunks": _CHILDREN,
    }
    payload.update(overrides)
    return store.stage_and_seal(**payload)  # type: ignore[arg-type]


def test_sella_bundle_content_addressed_cuando_es_nuevo(tmp_path: Path) -> None:
    store = _store(tmp_path)

    sealed = _seal(store)

    assert sealed.sealing_status is SealingStatus.SEALED
    assert sealed.bundle_dir_relpath == f"chunks/{_BUNDLE_ID}"
    bundle_dir = tmp_path / "projects" / "sst-general" / "chunks" / _BUNDLE_ID
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "parent_chunks.jsonl").exists()
    assert (bundle_dir / "child_chunks.jsonl").exists()
    assert (bundle_dir / "checksums.json").exists()
    assert set(sealed.checksums) == {
        "manifest.json",
        "parent_chunks.jsonl",
        "child_chunks.jsonl",
    }


def test_resellar_es_idempotente_cuando_el_contenido_coincide(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _seal(store)
    bundle_dir = tmp_path / "projects" / "sst-general" / "chunks" / _BUNDLE_ID
    before = {
        child.name: child.read_bytes() for child in sorted(bundle_dir.iterdir())
    }

    second = _seal(store)

    after = {
        child.name: child.read_bytes() for child in sorted(bundle_dir.iterdir())
    }
    assert second.checksums == first.checksums
    assert second.bundle_dir_relpath == first.bundle_dir_relpath
    assert after == before


def test_no_sobreescribe_bundle_referenciado_cuando_el_contenido_difiere(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    sealed = _seal(store)
    bundle_dir = tmp_path / "projects" / "sst-general" / "chunks" / _BUNDLE_ID
    before = {
        child.name: child.read_bytes() for child in sorted(bundle_dir.iterdir())
    }

    with pytest.raises(SealedBundleConflict):
        _seal(store, child_chunks=[{"chunk_id": "c1", "parent_id": "p1", "ordinal": 0, "text": "MUTADO"}])

    after = {
        child.name: child.read_bytes() for child in sorted(bundle_dir.iterdir())
    }
    assert after == before
    assert sealed.checksums["child_chunks.jsonl"]  # ruta/hash intactos


def test_identidad_invalida_no_deja_bundle_sellado(tmp_path: Path) -> None:
    # Fail-closed: un fingerprint inválido se rechaza ANTES de promover; no debe
    # quedar checksums.json (marker de commit) ni un directorio sellado.
    store = _store(tmp_path)

    with pytest.raises(ValidationError):
        _seal(store, chunking_profile_fingerprint="no-es-hex")

    bundle_dir = tmp_path / "projects" / "sst-general" / "chunks" / _BUNDLE_ID
    assert not (bundle_dir / "checksums.json").exists()
    assert not (bundle_dir / "manifest.json").exists()
