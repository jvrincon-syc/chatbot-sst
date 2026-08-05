from __future__ import annotations

from retrieval.fusion import RetrievedCandidate, reciprocal_rank_fusion
from retrieval.reranking import preserve_order_reranker


def test_reciprocal_rank_fusion_deduplicates_by_node_id_and_keeps_sources() -> None:
    vector = [
        RetrievedCandidate("n1", "texto", 0.9, "vector", {"page_number": 1}),
        RetrievedCandidate("n2", "otro", 0.8, "vector", {"page_number": 2}),
    ]
    lexical = [
        RetrievedCandidate("n2", "otro", 12.0, "lexical", {"page_number": 2}),
        RetrievedCandidate("n3", "mas", 4.0, "lexical", {"page_number": 3}),
    ]

    fused = reciprocal_rank_fusion([vector, lexical], k=60)

    assert [item.node_id for item in fused] == ["n2", "n1", "n3"]
    assert fused[0].metadata["retrieval_sources"] == ["vector", "lexical"]


def test_preserve_order_reranker_marks_original_scores() -> None:
    candidate = RetrievedCandidate("n1", "texto", 0.9, "vector", {})

    reranked = preserve_order_reranker([candidate])

    assert reranked[0].score == 0.9
    assert reranked[0].metadata["original_score"] == 0.9
