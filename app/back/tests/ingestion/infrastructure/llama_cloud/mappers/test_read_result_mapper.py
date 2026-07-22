from __future__ import annotations

from datetime import datetime, timezone

from ingestion.domain.models.parsed_document import (
    ParsedDocument,
    ParsedPage,
    ParsedPageMetadata,
)
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


def test_parsed_document_preserves_llamaparse_metadata_and_page_confidence() -> None:
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
            ParsedPage(page_number=1, markdown="Pagina confiable"),
            ParsedPage(page_number=2, markdown="Pagina para revisar"),
        ],
        page_metadata=[
            ParsedPageMetadata(
                page_number=1,
                metadata={
                    "confidence": 0.94,
                    "cost_optimized": False,
                    "triggered_auto_mode": True,
                },
            ),
            ParsedPageMetadata(
                page_number=2,
                metadata={"confidence": 0.76, "original_orientation_angle": 90},
            ),
        ],
        job_metadata={"credits": 2, "elapsed_seconds": 5.5},
    )

    result = parsed_document_to_read_result(parsed)

    assert result.pages[0].ocr_confidence.kind == "estimated"
    assert result.pages[0].ocr_confidence.value == 0.94
    assert result.pages[0].ocr_confidence.method == "llamaparse_page_parse_confidence"
    assert result.pages[0].ocr_confidence.provenance == "job_123"
    assert "llamaparse_confidence_not_word_ocr_measured" in result.pages[0].ocr_confidence.warnings
    assert result.pages[1].ocr_confidence.value == 0.76
    assert result.llama_cloud_metadata is not None
    assert result.llama_cloud_metadata.parse_job_id == "job_123"
    assert result.llama_cloud_metadata.parse_configuration_hash == "sha256:config"
    assert result.llama_cloud_metadata.page_metadata[0]["cost_optimized"] is False
    assert result.llama_cloud_metadata.job_metadata == {
        "credits": 2,
        "elapsed_seconds": 5.5,
    }


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
