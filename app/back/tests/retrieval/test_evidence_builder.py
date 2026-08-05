from __future__ import annotations

from retrieval.evidence_builder import EvidenceBuilder
from retrieval.fusion import RetrievedCandidate


def test_evidence_builder_preserves_document_section_page_scores_and_provenance() -> None:
    candidate = RetrievedCandidate(
        "n1",
        "Debe usar arnes.",
        0.91,
        "fusion",
        {
            "ref_doc_id": "doc_1",
            "document_name": "Manual SST",
            "section": "Alturas",
            "page_number": 4,
            "retrieval_sources": ["vector", "lexical"],
            "provider": "llamaparse",
            "processing_status": "processed",
        },
    )

    evidence = EvidenceBuilder().build([candidate])

    assert evidence[0]["document_id"] == "doc_1"
    assert evidence[0]["page_range"] == [4, 4]
    assert evidence[0]["scores"]["fusion"] == 0.91
    assert evidence[0]["provider_provenance"] == "llamaparse"
    assert evidence[0]["low_confidence"] is False
