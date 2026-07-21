from __future__ import annotations

from datetime import datetime, timezone

from ingestion.domain.models.parsed_document import ParsedDocument, ParsedPage
from ingestion.domain.models.provider import ProviderJobRef
from ingestion.infrastructure.llama_cloud.mappers.read_result_mapper import parsed_document_to_read_result


def test_parsed_document_maps_to_read_result_with_llamaparse_method() -> None:
    parsed = ParsedDocument(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="completed",
            configuration_hash="sha256:config",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ),
        markdown_pages=[ParsedPage(page_number=1, markdown="Texto")],
        job_metadata={"credits": 1},
        warnings=[],
    )

    result = parsed_document_to_read_result(parsed)

    assert result.extraction_method == "llamaparse"
    assert result.page_count == 1
    assert result.pages[0].extraction_method == "llamaparse"
    assert result.pages[0].text_normalized == "Texto"
    assert "llama_parse_job:job_123" in result.warnings


def test_parsed_document_maps_markdown_tables_to_tables_artifact() -> None:
    parsed = ParsedDocument(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="completed",
            configuration_hash="sha256:config",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ),
        markdown_pages=[
            ParsedPage(
                page_number=1,
                markdown="<table><tr><th>Codigo</th><th>Version</th></tr><tr><td>PL.RH-03SST</td><td>0.1</td></tr></table>",
            )
        ],
    )

    result = parsed_document_to_read_result(parsed)

    assert result.tables is not None
    assert result.tables.table_count == 1
    assert result.tables.tables[0].headers == ["Codigo", "Version"]
    assert result.tables.tables[0].rows == [["Codigo", "Version"], ["PL.RH-03SST", "0.1"]]


def test_parsed_document_maps_form_like_markdown_to_forms_artifact() -> None:
    parsed = ParsedDocument(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="completed",
            configuration_hash="sha256:config",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ),
        markdown_pages=[
            ParsedPage(
                page_number=1,
                markdown="## FORMATO PARA INTERPONER QUEJA\n\nNOMBRE COMPLETO: ____________________\n\nFIRMA DEL QUE INTERPONE LA QUEJA: ____________________",
            )
        ],
    )

    result = parsed_document_to_read_result(parsed)

    assert result.forms is not None
    assert result.forms.groups
    labels = [label.text for label in result.forms.groups[0].labels]
    assert "NOMBRE COMPLETO" in labels
    assert "FIRMA DEL QUE INTERPONE LA QUEJA" in labels


def test_parsed_document_marks_forms_as_evaluated_when_no_form_cues_are_found() -> None:
    parsed = ParsedDocument(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="completed",
            configuration_hash="sha256:config",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ),
        markdown_pages=[ParsedPage(page_number=1, markdown="# Politica SST\n\nContenido declarativo.")],
    )

    result = parsed_document_to_read_result(parsed)

    assert result.forms is not None
    assert result.forms.page_observations[0].status == "not_detected"


def test_parsed_document_does_not_detect_forms_from_procedural_mentions_only() -> None:
    parsed = ParsedDocument(
        provider_job=ProviderJobRef(
            provider="llama_cloud",
            capability="parse",
            job_id="job_123",
            status="completed",
            configuration_hash="sha256:config",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        ),
        markdown_pages=[
            ParsedPage(
                page_number=1,
                markdown="El comite puede recibir una queja y solicitar la firma del trabajador como parte del procedimiento.",
            )
        ],
    )

    result = parsed_document_to_read_result(parsed)

    assert result.forms is not None
    assert result.forms.groups == []
    assert result.forms.page_observations[0].status == "not_detected"
