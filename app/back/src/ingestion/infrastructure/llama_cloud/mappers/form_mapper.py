from __future__ import annotations

from ingestion.schemas.artifacts import FormGroup, FormLabel, FormsArtifact


def extracted_fields_to_forms_artifact(
    *,
    document_id: str,
    fields: dict[str, object],
    page_number: int,
) -> FormsArtifact:
    labels = [
        FormLabel(label_id=f"{document_id}_label_{index:03d}", text=name)
        for index, name in enumerate(fields, start=1)
    ]
    return FormsArtifact(
        schema_version="2.0",
        document_id=document_id,
        groups=[
            FormGroup(
                group_id=f"{document_id}_extract_group_001",
                page_number=page_number,
                labels=labels,
                controls=[],
                warnings=["generated_from_llama_extract_fields"],
            )
        ],
    )
