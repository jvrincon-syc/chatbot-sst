from __future__ import annotations

from typing import Any

from retrieval.fusion import RetrievedCandidate


class EvidenceBuilder:
    def __init__(self, *, low_confidence_threshold: float = 0.5) -> None:
        self._low_confidence_threshold = low_confidence_threshold

    def build(self, candidates: list[RetrievedCandidate]) -> list[dict[str, Any]]:
        return [self._build_one(candidate) for candidate in candidates]

    def _build_one(self, candidate: RetrievedCandidate) -> dict[str, Any]:
        page = candidate.metadata.get("page_number")
        return {
            "node_id": candidate.node_id,
            "document_id": candidate.metadata.get("ref_doc_id"),
            "document_name": candidate.metadata.get("document_name"),
            "section": candidate.metadata.get("section"),
            "page_range": [page, page] if page is not None else None,
            "text": candidate.text,
            "retrieval_source": candidate.source,
            "retrieval_sources": candidate.metadata.get(
                "retrieval_sources",
                [candidate.source],
            ),
            "scores": {candidate.source: candidate.score},
            "provider_provenance": candidate.metadata.get("provider"),
            "needs_review": candidate.metadata.get("processing_status") == "needs_review",
            "low_confidence": candidate.score < self._low_confidence_threshold,
        }
