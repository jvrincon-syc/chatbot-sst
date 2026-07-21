from __future__ import annotations

from ingestion.infrastructure.llama_cloud.mappers.form_mapper import extracted_fields_to_forms_artifact


def test_form_mapper_turns_extracted_fields_into_auditable_form_group() -> None:
    artifact = extracted_fields_to_forms_artifact(
        document_id="doc_123",
        fields={"nombre": "Ana", "queja": "Descripcion"},
        page_number=1,
    )

    assert artifact.document_id == "doc_123"
    assert artifact.groups[0].page_number == 1
    assert [label.text for label in artifact.groups[0].labels] == ["nombre", "queja"]
