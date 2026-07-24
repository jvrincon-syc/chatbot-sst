from __future__ import annotations

from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile, NormalizedDocumentBundle, PageTrace


def _bundle() -> NormalizedDocumentBundle:
    markdown = (
        "<!-- page: 1 -->\n\n"
        "Primer apartado con obligaciones SST.\n\n"
        "<!-- page: 2 -->\n\n"
        "Segundo apartado con responsabilidades y evidencias."
    )
    return NormalizedDocumentBundle(
        document_id="doc_engine",
        source_hash="a" * 64,
        corpus_version="phase1",
        source_relpath="manual/doc.pdf",
        normalized_relpath="manual/doc.md",
        markdown=markdown,
        page_traces=(
            PageTrace(
                page_number=1,
                char_start=0,
                char_end=54,
                text_raw="Primer apartado con obligaciones SST.",
                text_normalized="Primer apartado con obligaciones SST.",
            ),
            PageTrace(
                page_number=2,
                char_start=56,
                char_end=len(markdown),
                text_raw="Segundo apartado con responsabilidades y evidencias.",
                text_normalized="Segundo apartado con responsabilidades y evidencias.",
            ),
        ),
    )


def test_genera_bundle_desde_documento_normalizado() -> None:
    result = LocalChunkingEngine().chunk(
        document=_bundle(),
        profile=ChunkingProfile.local_structural_v1(),
    )

    assert result.document_id == "doc_engine"
    assert len(result.parents) == 1
    assert len(result.children) == 1
    assert result.parents[0].source_span.page_start == 1
    assert result.parents[0].source_span.page_end == 2
    assert result.children[0].parent_id == result.parents[0].chunk_id
