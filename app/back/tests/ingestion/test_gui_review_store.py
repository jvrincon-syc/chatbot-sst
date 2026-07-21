from pathlib import Path

import pytest

from ingestion.gui.review_store import (
    ReviewDecision,
    load_review_decisions,
    save_review_decision,
)


def test_save_review_decision_creates_schema_2_manifest(tmp_path: Path) -> None:
    path = tmp_path / "review_decisions.json"
    decision = ReviewDecision(
        document_id="doc_123",
        source_relpath="general_sst/manuales/test.pdf",
        decision="approved",
        reason="Revision humana completada.",
        decided_at="2026-07-20T10:00:00-05:00",
    )

    saved = save_review_decision(path, decision)

    assert saved == [decision]
    payload = path.read_text(encoding="utf-8")
    assert '"schema_version": "2.0"' in payload
    assert '"decision": "approved"' in payload


def test_save_review_decision_replaces_previous_document_decision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "review_decisions.json"
    first = ReviewDecision(
        document_id="doc_123",
        source_relpath="general_sst/manuales/test.pdf",
        decision="rejected",
        reason="Falta evidencia.",
        decided_at="2026-07-20T10:00:00-05:00",
    )
    second = ReviewDecision(
        document_id="doc_123",
        source_relpath="general_sst/manuales/test.pdf",
        decision="approved",
        reason="Corregido en revision manual.",
        decided_at="2026-07-20T11:00:00-05:00",
    )

    save_review_decision(path, first)
    saved = save_review_decision(path, second)

    assert saved == [second]
    assert load_review_decisions(path) == [second]


def test_review_decision_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="decision must be approved or rejected"):
        ReviewDecision(
            document_id="doc_123",
            source_relpath="general_sst/manuales/test.pdf",
            decision="pending",
            reason="No aplica.",
            decided_at="2026-07-20T10:00:00-05:00",
        )
