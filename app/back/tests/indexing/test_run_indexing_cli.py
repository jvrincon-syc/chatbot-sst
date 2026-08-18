from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.models import (
    ChunkBundle,
    ChunkingProfile,
    ChildChunk,
    ParentChunk,
    SourceSpan,
)
from ingestion.paths import ArtifactPaths
from indexing.domain.models import IndexableDocument
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pipeline_factory import LoadedChunkBundle
from scripts.indexing.run_indexing import finalize_postgres_connection
from scripts.indexing.run_indexing import run_indexing

_PROCESSING_PROFILE_FINGERPRINT = "c" * 64
_SEMANTIC_RECIPE_FINGERPRINT = "d" * 64


class StaticBundleLoader:
    def load(self, document: IndexableDocument) -> LoadedChunkBundle:
        return LoadedChunkBundle(
            bundle=_bundle(document.document_id),
            corpus_version="phase1",
            normalized_relpath=document.artifacts.markdown,
        )


def _bundle(document_id: str) -> ChunkBundle:
    profile = ChunkingProfile.local_structural_v1()
    parent = ParentChunk.create(
        document_id=document_id,
        profile_id=profile.profile_id,
        ordinal=0,
        text="Contenido SST para indexar",
        source_span=SourceSpan(
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=28,
        ),
        block_ids=("block-1",),
    )
    child = ChildChunk.create(
        document_id=document_id,
        profile_id=profile.profile_id,
        parent_id=parent.chunk_id,
        ordinal=0,
        text="Contenido SST para indexar",
        source_span=SourceSpan(
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=28,
        ),
        token_start=0,
        token_end=4,
        token_count=4,
        overlap_previous_tokens=0,
        overlap_next_tokens=0,
        overlap_previous_span=None,
        overlap_next_span=None,
        zero_overlap_reasons=frozenset({ZeroOverlapReason.DOCUMENT_START}),
    )
    return ChunkBundle(
        document_id=document_id,
        profile=profile,
        parents=(parent,),
        children=(child,),
    )


def test_run_indexing_indexes_approved_documents_with_llamaindex(tmp_path) -> None:
    normalized_root = tmp_path / "docs_normalized"
    manifests = normalized_root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        """
        {
          "records": [
            {
              "document_id": "doc_1",
              "source_relpath": "manual/doc.pdf",
              "processing_status": "processed",
              "source_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    result = run_indexing(
        normalized_root=normalized_root,
        only_sources=[],
        force=False,
        profile_id="llama-first-local-v1",
        dry_run=False,
        bundle_loader=StaticBundleLoader(),
    )

    assert result["status"] == "indexed"
    assert result["approved_documents"] == 1
    assert result["indexed_documents"] == 1
    assert result["indexed_parent_nodes"] == 1
    assert result["indexed_child_nodes"] == 1


def test_run_indexing_includes_human_approved_needs_review_documents(tmp_path) -> None:
    normalized_root = tmp_path / "docs_normalized"
    manifests = normalized_root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": "doc_processed",
                        "source_relpath": "manual/processed.pdf",
                        "processing_status": "processed",
                        "source_hash": "a" * 64,
                    },
                    {
                        "document_id": "doc_reviewed",
                        "source_relpath": "manual/reviewed.pdf",
                        "processing_status": "needs_review",
                        "source_hash": "b" * 64,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (manifests / "review_decisions.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "document_id": "doc_reviewed",
                        "source_relpath": "manual/reviewed.pdf",
                        "decision": "approved",
                        "reason": "Revision humana completada.",
                        "decided_at": "2026-07-28T10:00:00-05:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_indexing(
        normalized_root=normalized_root,
        only_sources=[],
        force=False,
        profile_id="llama-first-local-v1",
        dry_run=False,
        bundle_loader=StaticBundleLoader(),
    )

    assert result["status"] == "indexed"
    assert result["approved_documents"] == 2
    assert result["indexed_documents"] == 2


def test_run_indexing_blocks_postgres_without_confirmation(tmp_path) -> None:
    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="llama-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="llama_cloud",
        persist_confirmed=False,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "postgres_not_confirmed"


def test_run_indexing_blocks_postgres_without_dsn(tmp_path) -> None:
    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="llama-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="llama_cloud",
        persist_confirmed=True,
        environ={},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "postgres_dsn_missing"


def test_run_indexing_blocks_postgres_for_platform_owned_normalized_output(
    tmp_path,
    monkeypatch,
) -> None:
    _write_inventory(tmp_path, provider="platform", platform_owned=True)
    monkeypatch.setattr(
        "scripts.indexing.run_indexing._postgres_indexing_components",
        lambda **kwargs: pytest.fail("Task 5 must block before opening PostgreSQL"),
    )

    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="local-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "legacy_postgres_document_lane_blocked"
    assert (
        result["replacement_command"]
        == "npm run python -- scripts/rag_platform/rebuild_platform.py "
        "--project-id proj_demo --rag-variant-id ragv_demo"
    )


def test_run_indexing_blocks_postgres_when_metadata_sidecar_is_missing(
    tmp_path,
    monkeypatch,
) -> None:
    _write_inventory(tmp_path, provider="missing", write_metadata_sidecar=False)
    monkeypatch.setattr(
        "scripts.indexing.run_indexing._postgres_indexing_components",
        lambda **kwargs: pytest.fail("Task 5 must block before opening PostgreSQL"),
    )

    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="local-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "document_ownership_unverifiable"


def test_run_indexing_blocks_postgres_when_metadata_sidecar_is_invalid(
    tmp_path,
    monkeypatch,
) -> None:
    _write_inventory(tmp_path, provider="invalid", corrupt_metadata_sidecar=True)
    monkeypatch.setattr(
        "scripts.indexing.run_indexing._postgres_indexing_components",
        lambda **kwargs: pytest.fail("Task 5 must block before opening PostgreSQL"),
    )

    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="local-bge-m3-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "document_ownership_unverifiable"


def test_run_indexing_blocks_postgres_for_unsupported_live_provider(
    tmp_path,
    monkeypatch,
) -> None:
    _write_inventory(tmp_path, provider="mock")
    connection = RecordingConnection()
    monkeypatch.setattr(
        "scripts.indexing.run_indexing._postgres_indexing_components",
        lambda **kwargs: SimpleNamespace(
            profile=_resolved_profile(
                profile_id="llama-first-local-v1",
                ingestion_origin="local",
                embedding_provider="mock",
                embedding_model="deterministic",
                embedding_dimension=384,
                vector_table="idx_vec_llama_first_local_v1",
            ),
            indexer_kwargs={},
            connection=connection,
        ),
    )

    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="llama-first-local-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "unsupported_live_embedding_provider"
    assert result["embedding_provider"] == "mock"
    assert connection.calls == ["rollback", "close"]


def test_run_indexing_blocks_postgres_for_voyage_without_api_key(
    tmp_path,
    monkeypatch,
) -> None:
    _write_inventory(tmp_path, provider="voyage")
    connection = RecordingConnection()
    monkeypatch.setattr(
        "scripts.indexing.run_indexing._postgres_indexing_components",
        lambda **kwargs: SimpleNamespace(
            profile=_resolved_profile(
                profile_id="local-voyage-4-v1",
                ingestion_origin="local",
                embedding_provider="voyage",
                embedding_model="voyage-4",
                embedding_dimension=1024,
                vector_table="idx_vec_local_voyage_4_v1",
            ),
            indexer_kwargs={},
            connection=connection,
        ),
    )

    result = run_indexing(
        normalized_root=tmp_path,
        only_sources=[],
        force=False,
        profile_id="local-voyage-4-v1",
        dry_run=False,
        store="postgres",
        ingestion_origin="local",
        persist_confirmed=True,
        environ={"SST_POSTGRES_DSN": "postgresql://user:secret@localhost/sst"},
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "voyage_api_key_missing"
    assert result["required_secret"] == "VOYAGE_API_KEY"
    assert result["embedding_provider"] == "voyage"
    assert connection.calls == ["rollback", "close"]


def test_finalize_postgres_connection_commits_or_rolls_back_before_close() -> None:
    connection = RecordingConnection()

    finalize_postgres_connection(connection, succeeded=True)
    finalize_postgres_connection(connection, succeeded=False)

    assert connection.calls == ["commit", "close", "rollback", "close"]


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def _write_inventory(
    tmp_path,
    *,
    provider: str,
    write_metadata_sidecar: bool = True,
    platform_owned: bool = False,
    corrupt_metadata_sidecar: bool = False,
) -> None:
    manifests = tmp_path / "_manifests"
    manifests.mkdir(parents=True)
    source_relpath = f"manual/{provider}.pdf"
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "document_id": f"{provider}_doc",
                        "source_relpath": source_relpath,
                        "processing_status": "processed",
                        "source_hash": "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    if not write_metadata_sidecar:
        return
    _write_metadata_sidecar(
        normalized_root=tmp_path,
        source_relpath=source_relpath,
        document_id=f"{provider}_doc",
        platform_owned=platform_owned,
        corrupt=corrupt_metadata_sidecar,
    )


def _write_metadata_sidecar(
    *,
    normalized_root: Path,
    source_relpath: str,
    document_id: str,
    platform_owned: bool,
    corrupt: bool,
) -> None:
    metadata_path = normalized_root / Path(ArtifactPaths.for_source(source_relpath).metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        metadata_path.write_text("{invalid-json", encoding="utf-8")
        return
    payload = _metadata_payload(
        document_id=document_id,
        source_relpath=source_relpath,
        platform_owned=platform_owned,
    )
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")


def _metadata_payload(
    *,
    document_id: str,
    source_relpath: str,
    platform_owned: bool,
) -> dict[str, object]:
    normalized_relpath = ArtifactPaths.for_source(source_relpath).markdown
    unavailable = {"kind": "unavailable", "value": None}
    not_evaluated = {"status": "not_evaluated", "value": None}
    empty_field = {"value": None, "status": "not_evaluated"}
    platform_identity = None
    platform_provenance = None
    if platform_owned:
        platform_identity = {
            "project_id": "proj_demo",
            "source_document_id": "sdoc_demo",
            "source_document_revision_id": "srev_demo",
            "normalized_document_id": "ndoc_demo",
            "processing_profile_id": "pp_local",
            "processing_profile_fingerprint": _PROCESSING_PROFILE_FINGERPRINT,
            "schema_version": "2.0",
            "provenance": {
                "rag_variant_id": "ragv_demo",
                "semantic_recipe_fingerprint": _SEMANTIC_RECIPE_FINGERPRINT,
            },
        }
        platform_provenance = {
            "rag_variant_id": "ragv_demo",
            "semantic_recipe_fingerprint": _SEMANTIC_RECIPE_FINGERPRINT,
        }
    return {
        "schema_version": "2.0",
        "document_id": document_id,
        "document_name": Path(source_relpath).name,
        "source_relpath": source_relpath,
        "normalized_relpath": normalized_relpath,
        "document_control": {
            "title": empty_field,
            "code": empty_field,
            "version": empty_field,
            "publication_date": empty_field,
            "effective_date": empty_field,
            "warnings": [],
        },
        "classification": {
            "document_type": "otro",
            "document_type_confidence": unavailable,
            "topic": "general",
            "topic_confidence": unavailable,
            "signals": [],
            "conflicts": [],
            "warnings": [],
        },
        "page_count": 1,
        "language": "es",
        "extraction_method": "markdown",
        "ocr_confidence": unavailable,
        "handwriting": not_evaluated,
        "tables": not_evaluated,
        "forms": not_evaluated,
        "feature_observations": {},
        "source_hash": "a" * 64,
        "corpus_version": "phase1",
        "pipeline_version": "2.0.0",
        "processing_status": "processed",
        "review_reasons": [],
        "warnings": [],
        "platform_identity": platform_identity,
        "platform_provenance": platform_provenance,
    }



def _resolved_profile(
    *,
    profile_id: str,
    ingestion_origin: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimension: int,
    vector_table: str,
) -> ResolvedIndexingProfile:
    return ResolvedIndexingProfile(
        profile_id=profile_id,
        ingestion_origin=ingestion_origin,
        chunking_version="structure-aware-v1",
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        distance_metric="cosine",
        vector_table=vector_table,
        metadata_schema_version="2.0",
        active=True,
        config_hash="a" * 64,
    )
