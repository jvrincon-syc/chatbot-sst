from __future__ import annotations

from datetime import datetime, timezone

from rag_platform.domain.artifact_catalog import (
    NormalizedDocumentArtifactRecord,
    RawDocumentArtifactRecord,
)
from rag_platform.domain.models import ProcessingOrigin
from rag_platform.infrastructure.postgres.artifact_catalog_repositories import (
    PostgresNormalizedArtifactCatalogRepository,
    PostgresRawArtifactCatalogRepository,
)


def test_raw_catalog_upsert_es_idempotente_por_revision() -> None:
    connection = RecordingConnection()
    repository = PostgresRawArtifactCatalogRepository(connection)

    stored = repository.upsert(_raw_record())
    again = repository.upsert(_raw_record())

    assert again == stored
    assert len(connection.cursor_obj.statements) == 2
    assert "ON CONFLICT (source_document_revision_id) DO UPDATE SET" in (
        connection.cursor_obj.statements[0]
    )
    assert connection.cursor_obj.params[0][0] == "srev_manual"


def test_normalized_catalog_actualiza_variant_provenance_sin_cambiar_identidad() -> None:
    connection = RecordingConnection()
    repository = PostgresNormalizedArtifactCatalogRepository(connection)

    base = repository.upsert(_normalized_record(rag_variant_id=None, recipe=None))
    enriched = repository.upsert(
        _normalized_record(rag_variant_id="ragv_local-bge", recipe="c" * 64)
    )

    assert enriched.normalized_document_id == base.normalized_document_id
    assert enriched.rag_variant_id == "ragv_local-bge"
    statement = connection.cursor_obj.statements[1]
    params = connection.cursor_obj.params[1]
    assert "ON CONFLICT (project_id, source_document_revision_id," in statement
    assert "processing_profile_fingerprint) DO UPDATE SET" in statement
    assert "normalized_document_id = EXCLUDED.normalized_document_id" not in statement
    assert params[4] == "ragv_local-bge"
    assert params[5] == "c" * 64


def _raw_record() -> RawDocumentArtifactRecord:
    return RawDocumentArtifactRecord(
        project_id="proj_sst-general",
        source_document_revision_id="srev_manual",
        logical_document_id="sdoc_manual",
        artifact_relpath="raw/general/manual.pdf",
        source_relpath="general/manual.pdf",
        raw_content_hash="a" * 64,
        file_size=128,
        uploaded_by="operator",
        uploaded_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def _normalized_record(
    *, rag_variant_id: str | None, recipe: str | None
) -> NormalizedDocumentArtifactRecord:
    provenance = (
        {}
        if rag_variant_id is None
        else {
            "rag_variant_id": rag_variant_id,
            "semantic_recipe_fingerprint": recipe,
        }
    )
    return NormalizedDocumentArtifactRecord(
        normalized_document_id="ndoc_manual",
        project_id="proj_sst-general",
        source_document_revision_id="srev_manual",
        logical_document_id="sdoc_manual",
        processing_profile_id="pp_local-pdf",
        processing_profile_fingerprint="b" * 64,
        processing_origin=ProcessingOrigin.LOCAL,
        parser_provider="local",
        parser_engine="pdfium",
        observed_revision="2026.08.12",
        schema_version="2.0",
        markdown_relpath="normalized/general/manual.md",
        metadata_relpath="normalized/general/manual.metadata.json",
        pages_relpath="normalized/general/manual.pages.json",
        tables_relpath="normalized/general/manual.tables.json",
        forms_relpath="normalized/general/manual.forms.json",
        source_hash="a" * 64,
        processing_status="processed",
        provenance=provenance,
    )


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()

    def cursor(self) -> "RecordingCursor":
        return self.cursor_obj


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[tuple[object, ...]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def execute(self, statement: str, params: tuple[object, ...]) -> None:
        self.statements.append(statement)
        self.params.append(params)
