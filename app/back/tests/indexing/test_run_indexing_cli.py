from __future__ import annotations

from ingestion.schemas.artifacts import MetadataArtifact, PageRecord, PagesArtifact
from indexing.domain.models import IndexableDocument
from indexing.infrastructure.llama_index.pipeline_factory import NormalizedBundleArtifacts
from scripts.indexing.run_indexing import run_indexing
from scripts.indexing.run_indexing import finalize_postgres_connection


class StaticBundleLoader:
    def load(self, document: IndexableDocument) -> NormalizedBundleArtifacts:
        classification = type(
            "ClassificationStub",
            (),
            {"document_type": "manual", "topic": "SST", "subtopic": None},
        )()
        metadata = MetadataArtifact.model_construct(
            document_id=document.document_id,
            document_name="Manual SST",
            source_relpath=document.source_relpath,
            normalized_relpath=document.artifacts.markdown,
            classification=classification,
            page_count=1,
            extraction_method="llamaparse",
            source_hash=document.source_hash,
            corpus_version="phase1",
            pipeline_version="2.0.0",
            processing_status=document.document_status,
            review_reasons=[],
            warnings=[],
        )
        pages = PagesArtifact.model_construct(
            document_id=document.document_id,
            page_count=1,
            pages=[
                PageRecord.model_construct(
                    page_number=1,
                    text_normalized="Contenido SST para indexar",
                    blocks=[],
                )
            ],
        )
        return NormalizedBundleArtifacts(
            markdown="<!-- page: 1 -->\n\nContenido SST para indexar.",
            metadata=metadata,
            pages=pages,
            processing_fingerprint=document.source_hash,
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
