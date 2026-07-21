from __future__ import annotations

from ingestion.schemas.artifacts import MetadataArtifact, PageRecord, PagesArtifact
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.llama_index.document_factory import (
    NormalizedDocumentFactory,
)


def _profile() -> IndexingProfile:
    return IndexingProfile(
        profile_id="llama-first-local-v1",
        chunking_version="structure-aware-v1",
        embedding_provider="mock",
        embedding_model="deterministic",
        embedding_dimension=3,
        vector_store="memory",
        metadata_schema_version="2.0",
    )


def _metadata() -> MetadataArtifact:
    classification = type(
        "ClassificationStub",
        (),
        {
            "document_type": "manual",
            "topic": "Trabajo en alturas",
            "subtopic": "Arnes",
        },
    )()
    return MetadataArtifact.model_construct(
        document_id="doc_abc",
        document_name="Manual SST",
        source_relpath="manual/sst.pdf",
        normalized_relpath="manual/sst.md",
        classification=classification,
        page_count=2,
        extraction_method="llamaparse",
        source_hash="b" * 64,
        corpus_version="phase1",
        pipeline_version="2.0.0",
        processing_status="processed",
        review_reasons=[],
        warnings=[],
    )


def _pages() -> PagesArtifact:
    return PagesArtifact.model_construct(
        document_id="doc_abc",
        page_count=2,
        pages=[
            PageRecord.model_construct(
                page_number=1,
                text_normalized="Titulo pagina uno",
                blocks=[],
            ),
            PageRecord.model_construct(
                page_number=2,
                text_normalized="Titulo pagina dos",
                blocks=[],
            ),
        ],
    )


def test_document_factory_creates_llama_document_with_stable_id_and_metadata() -> None:
    markdown = """---
document_id: doc_abc
source_hash: bbbbb
---

<!-- page: 1 -->

# Titulo

Contenido pagina uno.

<!-- page: 2 -->

Contenido pagina dos.
"""

    document = NormalizedDocumentFactory().create_document(
        markdown=markdown,
        metadata=_metadata(),
        pages=_pages(),
        profile=_profile(),
        processing_fingerprint="fingerprint-1",
    )

    assert document.id_ == "doc_abc"
    assert document.text.startswith("<!-- page: 1 -->")
    assert "source_hash: bbbbb" not in document.text
    assert document.metadata["ref_doc_id"] == "doc_abc"
    assert document.metadata["document_type"] == "manual"
    assert document.metadata["topic"] == "Trabajo en alturas"
    assert document.metadata["page_catalog"] == [
        {"page_number": 1, "char_start": 0, "char_end": 49},
        {"page_number": 2, "char_start": 51, "char_end": 90},
    ]
    assert "source_hash" in document.excluded_embed_metadata_keys
    assert "page_catalog" in document.excluded_embed_metadata_keys
    assert "topic" not in document.excluded_embed_metadata_keys


def test_document_factory_uses_pages_artifact_when_markdown_has_no_page_markers() -> None:
    document = NormalizedDocumentFactory().create_document(
        markdown="Texto sin marcadores",
        metadata=_metadata(),
        pages=_pages(),
        profile=_profile(),
        processing_fingerprint="fingerprint-1",
    )

    assert document.metadata["page_catalog"] == [
        {"page_number": 1, "char_start": 0, "char_end": 20},
        {"page_number": 2, "char_start": 0, "char_end": 20},
    ]
