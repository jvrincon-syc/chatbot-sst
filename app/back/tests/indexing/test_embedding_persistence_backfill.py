from __future__ import annotations

import json
from pathlib import Path

from scripts.indexing.backfill_embedding_persistence import (
    VECTOR_TABLES,
    ChunkBundleLedgerRecord,
    collect_chunk_bundle_records,
    dry_run_summary,
    target_id_for_vector_table,
)
from scripts.indexing.prepare_postgres_indexing import REQUIRED_BASE_TABLES


def test_prepare_postgres_requires_embedding_persistence_tables() -> None:
    required = set(REQUIRED_BASE_TABLES)

    assert "indexing_targets" in required
    assert "chunk_bundles" in required
    assert "embedding_runs" in required
    assert "embedding_bundles" in required
    assert "embedding_bundle_chunks" in required
    assert "readiness_checks" in required
    assert "retrieval_profiles" in required


def test_target_id_for_vector_table_is_deterministic() -> None:
    assert target_id_for_vector_table("idx_vec_local_bge_m3_v1") == (
        "target-idx-vec-local-bge-m3-v1"
    )


def test_collect_chunk_bundle_records_reads_metadata_without_chunk_text(tmp_path: Path) -> None:
    metadata_path = tmp_path / "manual" / "doc.chunking_metadata.json"
    metadata_path.parent.mkdir()
    metadata_path.write_text(
        json.dumps(
            {
                "document_id": "doc_1",
                "bundle_fingerprint": "chunk-bundle-abc",
                "profile_id": "local-structural-v1",
                "profile_fingerprint": "chunking-profile-abc",
                "corpus_version": "phase1",
                "normalized_relpath": "manual/doc.md",
                "parent_count": 2,
                "child_count": 3,
            }
        ),
        encoding="utf-8",
    )

    records = collect_chunk_bundle_records(tmp_path)

    assert records == [
        ChunkBundleLedgerRecord(
            chunk_bundle_id="chunk-bundle-abc",
            bundle_fingerprint="chunk-bundle-abc",
            profile_id="local-structural-v1",
            profile_fingerprint="chunking-profile-abc",
            corpus_version="phase1",
            source_document_id="doc_1",
            artifact_relpath="manual/doc.chunking_metadata.json",
            parent_count=2,
            child_count=3,
            status="legacy_unverified",
        )
    ]


def test_dry_run_summary_classifies_legacy_without_activation(tmp_path: Path) -> None:
    summary = dry_run_summary(chunks_root=tmp_path)

    assert summary["mode"] == "dry_run"
    assert summary["vector_tables"] == len(VECTOR_TABLES)
    assert summary["retrieval_profiles_activated"] == 0
    assert "compatibility_not_proven" in summary["legacy_statuses"]
