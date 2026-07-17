from ingestion.document_control import extract_document_control


def test_extracts_deduplicated_repeated_header_fields() -> None:
    pages = [
        {"page_number": 1, "text_raw": "# Procedimiento\nCodigo: PR-SST-01\nVersion: 02\nFecha de publicacion: 2026-01-10"},
        {"page_number": 2, "text_raw": "Codigo: PR-SST-01\nVersion: 02"},
    ]
    control = extract_document_control(pages, "PR-SST-01_20301231.pdf")
    assert control.code.value == "PR-SST-01"
    assert control.code.value_raw == "PR-SST-01"
    assert len(control.code.evidence) == 2
    assert control.version.value == "02"
    assert control.publication_date.value == "2026-01-10"


def test_extracts_visible_title_block_role() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": "Codigo: PR-SST-01",
            "blocks": [
                {
                    "text": "Procedimiento de auditoria",
                    "role": "title",
                    "extraction_method": "pdf_digital",
                },
                {"text": "Codigo: PR-SST-01", "extraction_method": "pdf_digital"},
            ],
        }
    ]

    control = extract_document_control(pages, "procedimiento.pdf")

    assert control.title.value == "Procedimiento de auditoria"
    assert control.title.evidence[0].source == "pdf_digital"


def test_preserves_raw_code_while_normalizing_delimiter_only() -> None:
    control = extract_document_control([{"page_number": 1, "text_raw": "Codigo: fr - sst - 01"}], "x.pdf")
    assert control.code.value == "FR-SST-01"
    assert control.code.value_raw == "fr - sst - 01"


def test_not_found_and_filename_timestamp_is_not_a_documentary_date() -> None:
    control = extract_document_control([{"page_number": 1, "text_raw": "# Nota\nContenido"}], "nota_2026-01-10.pdf")
    assert control.code.status == "not_found"
    assert control.publication_date.status == "not_found"
    assert control.effective_date.status == "not_found"


def test_keeps_conflicting_ocr_and_header_codes_without_repair() -> None:
    pages = [{"page_number": 1, "text_raw": "Codigo: PR-SST-01\nCodigo: PR-5ST-01"}]
    control = extract_document_control(pages, "x.pdf")
    assert control.code.status == "conflicting"
    assert control.code.value == ["PR-SST-01", "PR-5ST-01"]
    assert "conflicting_code" in control.warnings


def test_extracts_visible_history_rows() -> None:
    pages = [{"page_number": 1, "text_raw": "Historial de cambios\n| Version | Fecha | Descripcion |\n| 02 | 2026-01-10 | Ajuste anual |"}]
    control = extract_document_control(pages, "x.pdf")
    assert len(control.change_history) == 1
    assert control.change_history[0].version == "02"
    assert control.change_history[0].date == "2026-01-10"


def test_history_extraction_stops_before_unrelated_tables() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "Historial de cambios\n"
                "| Version | Fecha | Descripcion |\n"
                "| 02 | 2026-01-10 | Ajuste anual |\n\n"
                "## Tabla de actividades\n"
                "| Actividad | Fecha |\n"
                "| Auditoria | 2026-02-01 |"
            ),
        }
    ]

    control = extract_document_control(pages, "x.pdf")

    assert len(control.change_history) == 1
