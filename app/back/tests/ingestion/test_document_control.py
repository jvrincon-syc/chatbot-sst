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


def test_extracts_conservative_plain_pdf_title_from_first_page() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO\n"
                "CÃ³digo: RE.RH-04 SST\n"
                "VersiÃ³n: 0.3\n"
                "Datos de la persona que interpone la queja"
            ),
        }
    ]

    control = extract_document_control(pages, "formato.pdf")

    assert control.title.value == "FORMATO PARA INTERPONER QUEJA POR PRESUNTO ACOSO"


def test_code_pattern_does_not_treat_hyphenated_prose_as_document_codes() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "MANUAL DE CONVIVENCIA LABORAL\n"
                "M.RH-03-SST\n"
                "La convivencia laboral-no constituye una sanciÃ³n.\n"
                "Consulte www.syc.com.co"
            ),
        }
    ]

    control = extract_document_control(pages, "manual.pdf")

    assert control.code.status == "extracted"
    assert control.code.value == "M-RH-03-SST"


def test_version_pattern_does_not_consume_unrelated_prose() -> None:
    control = extract_document_control(
        [
            {
                "page_number": 1,
                "text_raw": (
                    "REGLAMENTO DEL COMITÃ‰\n"
                    "Se escucharÃ¡n las versiones de los hechos."
                ),
            }
        ],
        "reglamento.pdf",
    )

    assert control.version.status == "not_found"


def test_uses_page_text_when_layout_blocks_split_control_label_and_value() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "MANUAL DE CONVIVENCIA LABORAL\n"
                "CODIGO M.RH-03-SST VERSION 0.2"
            ),
            "blocks": [
                {"text": "MANUAL DE CONVIVENCIA LABORAL", "role": "body"},
                {"text": "CODIGO", "role": "body"},
                {"text": "M.RH-03-SST", "role": "body"},
                {"text": "VERSION", "role": "body"},
                {"text": "0.2", "role": "body"},
            ],
        }
    ]

    control = extract_document_control(pages, "manual.pdf")

    assert control.code.value == "M-RH-03-SST"
    assert control.version.value == "0.2"


def test_prefers_specific_plain_title_over_corporate_header() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "PROCESOS ADMINISTRATIVOS / SEGURIDAD Y SALUD EN EL TRABAJO\n"
                "MANUAL DE CONVIVENCIA LABORAL\n"
                "CODIGO M.RH-03-SST VERSION 0.2"
            ),
        }
    ]

    control = extract_document_control(pages, "manual.pdf")

    assert control.title.value == "MANUAL DE CONVIVENCIA LABORAL"


def test_later_referenced_code_does_not_override_first_page_control_code() -> None:
    pages = [
        {
            "page_number": 1,
            "text_raw": (
                "MANUAL DE CONVIVENCIA LABORAL\n"
                "CODIGO M.RH-03-SST VERSION 0.2"
            ),
        },
        {
            "page_number": 2,
            "text_raw": "Consulte el formato RE-RH-004-SST para presentar una queja.",
        },
    ]

    control = extract_document_control(pages, "manual.pdf")

    assert control.code.status == "extracted"
    assert control.code.value == "M-RH-03-SST"
