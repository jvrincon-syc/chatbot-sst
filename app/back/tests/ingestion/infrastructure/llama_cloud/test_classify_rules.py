from __future__ import annotations

from ingestion.infrastructure.llama_cloud.classify_rules import classification_labels


def test_classification_labels_cover_internal_document_types_with_rules() -> None:
    labels = classification_labels()

    assert "formulario" in labels
    assert "manual" in labels
    assert labels["formulario"]
    assert any("formato" in rule.lower() for rule in labels["formulario"])
