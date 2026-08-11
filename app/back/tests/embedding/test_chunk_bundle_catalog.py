from __future__ import annotations

from embedding.domain.errors import ChunkBundleNotFound
from embedding.infrastructure.filesystem.chunk_bundle_catalog import (
    FilesystemChunkBundleCatalogRepository,
    HybridChunkBundleRepository,
)
from embedding.infrastructure.in_memory.repositories import InMemoryChunkBundleRepository

from pipeline_fixtures import write_chunk_bundle


def test_catalogo_filesystem_expone_chunk_bundles_nuevos(tmp_path) -> None:
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    repository = FilesystemChunkBundleCatalogRepository(chunks_root=tmp_path / "chunks")

    bundles = repository.list_bundles()

    assert len(bundles) == 1
    assert bundles[0].chunk_bundle_id == chunk_bundle.chunk_bundle_id
    assert bundles[0].artifact_relpath.endswith(".chunking_metadata.json")
    assert bundles[0].source_relpath == "unit/example.md"
    assert bundles[0].normalized_relpath == "unit/example.md"
    assert bundles[0].source_hash is not None
    assert bundles[0].status == "verified"


def test_catalogo_filesystem_falla_cerrado_si_no_existe_el_bundle(tmp_path) -> None:
    repository = FilesystemChunkBundleCatalogRepository(chunks_root=tmp_path / "chunks")

    try:
        repository.get("chunk-bundle-missing")
    except ChunkBundleNotFound:
        return
    raise AssertionError("expected ChunkBundleNotFound")


def test_hybrid_registra_en_el_ledger_un_bundle_solo_presente_en_filesystem(tmp_path) -> None:
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    repository = HybridChunkBundleRepository(
        primary=InMemoryChunkBundleRepository(),
        filesystem=FilesystemChunkBundleCatalogRepository(chunks_root=tmp_path / "chunks"),
    )

    visible = repository.get(chunk_bundle.chunk_bundle_id)
    stored = repository.ensure_registered(visible)

    assert stored.chunk_bundle_id == chunk_bundle.chunk_bundle_id
    assert repository.list_bundles()[0].artifact_relpath.endswith(".chunking_metadata.json")


def test_hybrid_prefiere_el_bundle_canonico_del_filesystem_sobre_el_legacy(tmp_path) -> None:
    chunk_bundle = write_chunk_bundle(tmp_path / "chunks")
    legacy = chunk_bundle.model_copy(
        update={
            "chunk_bundle_id": f"legacy-{chunk_bundle.chunk_bundle_id}",
            "artifact_relpath": chunk_bundle.source_relpath or "legacy.md",
            "parent_count": 0,
            "child_count": 0,
            "status": "legacy_unverified",
        }
    )
    repository = HybridChunkBundleRepository(
        primary=InMemoryChunkBundleRepository([legacy]),
        filesystem=FilesystemChunkBundleCatalogRepository(chunks_root=tmp_path / "chunks"),
    )

    bundles = repository.list_bundles()

    assert len(bundles) == 1
    assert bundles[0].chunk_bundle_id == chunk_bundle.chunk_bundle_id
    assert bundles[0].artifact_relpath.endswith(".chunking_metadata.json")
    assert bundles[0].child_count == chunk_bundle.child_count
