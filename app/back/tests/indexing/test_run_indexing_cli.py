from __future__ import annotations

import json
from types import SimpleNamespace

from chunking.domain.enums import ZeroOverlapReason
from chunking.domain.models import (
    ChunkBundle,
    ChunkingProfile,
    ChildChunk,
    ParentChunk,
    SourceSpan,
)
from indexing.domain.models import IndexableDocument
from indexing.domain.profiles import ResolvedIndexingProfile
from indexing.infrastructure.llama_index.pipeline_factory import LoadedChunkBundle
from scripts.indexing.run_indexing import finalize_postgres_connection
from scripts.indexing.run_indexing import run_indexing


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


def _write_inventory(tmp_path, *, provider: str) -> None:
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
