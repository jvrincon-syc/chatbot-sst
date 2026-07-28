from __future__ import annotations

from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile, NormalizedDocumentBundle, PageTrace
from indexing.domain.models import IndexingProfile
from indexing.infrastructure.embeddings.bge import BgeEmbeddingProvider
from indexing.infrastructure.embeddings.settings import EmbeddingSettings


def _bundle() -> NormalizedDocumentBundle:
    markdown = (
        "<!-- page: 1 -->\n\n"
        "Alcance\n\n"
        "Este procedimiento define el control local de incidentes SST.\n\n"
        "Se conserva trazabilidad de cada evidencia.\n\n"
        "Para cada incidente generar un informe"
    )
    return NormalizedDocumentBundle(
        document_id="doc_simple_chunk",
        source_hash="b" * 64,
        corpus_version="phase1",
        source_relpath="manual/simple.pdf",
        normalized_relpath="manual/simple.md",
        markdown=markdown,
        page_traces=(
            PageTrace(
                page_number=1,
                char_start=0,
                char_end=len(markdown),
                text_raw=markdown,
                text_normalized=markdown,
            ),
        ),
    )


def _profile() -> IndexingProfile:
    return IndexingProfile(
        profile_id="local-bge-m3-v1",
        chunking_version="structure-aware-v1",
        embedding_provider="bge",
        embedding_model="BAAI/bge-m3",
        embedding_dimension=1024,
        vector_store="memory",
        metadata_schema_version="2.0",
    )


def test_embedding_smoke_chunks_simple_text_and_uses_local_hf_model() -> None:
    chunk_result = LocalChunkingEngine().chunk(
        document=_bundle(),
        profile=ChunkingProfile.local_structural_v1(),
    )

    provider = BgeEmbeddingProvider(
        profile=_profile(),
        settings=EmbeddingSettings(
            provider="bge",
            batch_size=8,
            hf_hub_cache=_hf_cache(),
        ),
    )

    batch = provider.embed_documents([child.text for child in chunk_result.children])

    assert len(chunk_result.parents) == 1
    assert len(chunk_result.children) == 1
    assert chunk_result.children[0].text.startswith("Alcance")
    assert batch.provider == "bge"
    assert batch.model == "BAAI/bge-m3"
    assert batch.dimension == 1024
    assert len(batch.vectors) == 1
    assert len(batch.vectors[0]) == 1024


def _hf_cache() -> str | None:
    import os

    cache = os.environ.get("HF_HUB_CACHE")
    return cache or None
