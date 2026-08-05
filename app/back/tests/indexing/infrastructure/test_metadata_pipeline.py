from __future__ import annotations

from llama_index.core.schema import TextNode

from indexing.infrastructure.llama_index.metadata_pipeline import (
    MetadataEnrichmentPipeline,
)


def test_metadata_pipeline_keeps_deterministic_metadata_and_skips_generative_by_default() -> None:
    node = TextNode(
        id_="node_1",
        text="Contenido sobre trabajo seguro en alturas.",
        metadata={
            "ref_doc_id": "doc_1",
            "document_type": "manual",
            "topic": "SST",
            "page_number": 3,
        },
    )

    enriched = MetadataEnrichmentPipeline().apply([node])

    assert enriched[0].metadata["ref_doc_id"] == "doc_1"
    assert enriched[0].metadata["page_number"] == 3
    assert "generated_summary" not in enriched[0].metadata


def test_metadata_pipeline_can_add_explicit_generative_metadata_with_version() -> None:
    node = TextNode(id_="node_1", text="Texto", metadata={"ref_doc_id": "doc_1"})

    enriched = MetadataEnrichmentPipeline(
        generative_metadata={
            "node_1": {
                "generated_summary": "Resumen controlado",
                "generated_keywords": ["sst"],
            }
        },
        generation_version="summary-v1",
    ).apply([node])

    assert enriched[0].metadata["generated_summary"] == "Resumen controlado"
    assert enriched[0].metadata["generated_keywords"] == ["sst"]
    assert enriched[0].metadata["generation_version"] == "summary-v1"
