from __future__ import annotations

from retrieval.vector_retriever import VectorCandidate, VectorRetriever


def test_vector_retriever_applies_metadata_filters_and_returns_scores() -> None:
    retriever = VectorRetriever(
        candidates=[
            VectorCandidate(
                node_id="n1",
                text="uso de arnes certificado",
                embedding=[1.0, 0.0],
                metadata={
                    "document_type": "manual",
                    "topic": "SST",
                    "processing_status": "processed",
                },
            ),
            VectorCandidate(
                node_id="n2",
                text="comite convivencia",
                embedding=[0.0, 1.0],
                metadata={
                    "document_type": "formulario",
                    "topic": "Convivencia",
                    "processing_status": "needs_review",
                },
            ),
        ]
    )

    results = retriever.search(
        query_embedding=[1.0, 0.0],
        filters={"document_type": "manual", "processing_status": "processed"},
        top_k=3,
    )

    assert [result.node_id for result in results] == ["n1"]
    assert results[0].score == 1.0
    assert results[0].metadata["topic"] == "SST"
