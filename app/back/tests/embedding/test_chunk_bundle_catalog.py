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


def test_catalogo_chunk_lee_variant_provenance_desde_chunking_metadata(tmp_path) -> None:
    # Task 6: el catálogo reconstruye el ChunkBundleRef con project_id + provenance de
    # variante escrita por el chunking de plataforma en el sidecar.
    import json
    from pathlib import Path

    base = tmp_path / "chunks" / "general" / "doc"
    base.parent.mkdir(parents=True, exist_ok=True)
    Path(f"{base}.chunking_metadata.json").write_text(
        json.dumps(
            {
                "document_id": "doc_1",
                "bundle_fingerprint": "chunk_1",
                "profile_id": "local-structural-v1",
                "profile_fingerprint": "a" * 64,
                "corpus_version": "platform",
                "source_hash": "c" * 64,
                "project_id": "proj_sst-general",
                "source_document_revision_id": "srev_manual",
                "normalized_document_id": "ndoc_manual",
                "rag_variant_id": "ragv_local_bge",
                "semantic_recipe_fingerprint": "b" * 64,
                "parent_count": 2,
                "child_count": 3,
            }
        ),
        encoding="utf-8",
    )
    repo = FilesystemChunkBundleCatalogRepository(chunks_root=tmp_path / "chunks")

    bundle = repo.get("chunk_1")

    assert bundle.project_id == "proj_sst-general"
    assert bundle.rag_variant_id == "ragv_local_bge"
    assert bundle.semantic_recipe_fingerprint == "b" * 64
