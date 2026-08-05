from __future__ import annotations

from types import SimpleNamespace

from indexing.application.eligibility import IndexingEligibilityService


def test_processed_document_is_eligible() -> None:
    result = IndexingEligibilityService().evaluate(
        record={
            "document_id": "doc_1",
            "source_relpath": "manual/doc.pdf",
            "processing_status": "processed",
            "source_hash": "a" * 64,
            "ingestion_provider": "llama_cloud",
        },
        decision=None,
    )

    assert result.eligible is True
    assert result.reason == "processed"


def test_needs_review_without_approval_is_excluded() -> None:
    result = IndexingEligibilityService().evaluate(
        record={
            "document_id": "doc_2",
            "source_relpath": "manual/review.pdf",
            "processing_status": "needs_review",
            "source_hash": "b" * 64,
            "ingestion_provider": "llama_cloud",
        },
        decision=None,
    )

    assert result.eligible is False
    assert result.reason == "needs_review_without_approval"


def test_needs_review_with_approved_decision_is_eligible() -> None:
    result = IndexingEligibilityService().evaluate(
        record={
            "document_id": "doc_3",
            "source_relpath": "manual/reviewed.pdf",
            "processing_status": "needs_review",
            "source_hash": "c" * 64,
            "ingestion_provider": "llama_cloud",
        },
        decision=SimpleNamespace(decision="approved"),
    )

    assert result.eligible is True
    assert result.reason == "human_approved"
