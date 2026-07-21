from pathlib import Path

import pytest

from ingestion.classification.rules import ClassificationResult, classify_document
from ingestion.document_control import extract_document_control


def _control(title: str):
    return extract_document_control([{"page_number": 1, "text_raw": f"# {title}"}], "documento.pdf")


def test_title_beats_manual_route_for_a_form() -> None:
    result = classify_document("general/manuales/inspeccion.pdf", [{"text_raw": "# Formato de inspeccion"}], _control("Formato de inspeccion"))
    assert isinstance(result, ClassificationResult)
    assert result.document_type == "formulario"
    assert result.document_type_confidence.value == 0.95
    assert result.conflict_status == "none"
    assert result.conflicts == []


def test_title_beats_capacitaciones_route_for_program() -> None:
    result = classify_document("sst/capacitaciones/programa.pdf", [{"text_raw": "# Programa anual"}], _control("Programa anual"))
    assert result.document_type == "programa"
    assert result.conflict_status == "none"
    assert result.conflicts == []


def test_title_beats_policy_route_for_matrix_without_folder_conflict() -> None:
    result = classify_document("sst/politica/matriz.pdf", [{"text_raw": "# Matriz de riesgos"}], _control("Matriz de riesgos"))
    assert result.document_type == "matriz"
    assert result.conflict_status == "none"
    assert result.conflicts == []


def test_objectives_and_metrics_title_is_classified_as_matrix() -> None:
    result = classify_document(
        "general_sst/capacitaciones/politica_seguridad_trabajo/"
        "seguridad_vial/documento.pdf",
        [{"text_raw": "La matriz define indicadores de medicion."}],
        _control("Objetivos y metas de seguridad vial"),
    )

    assert result.document_type == "matriz"


def test_specific_security_vial_route_beats_generic_capacitaciones_container() -> None:
    result = classify_document(
        "general_sst/capacitaciones/politica_seguridad_trabajo/"
        "seguridad_vial/objetivos.pdf",
        [{"text_raw": "# OBJETIVOS Y METAS\n\nMatriz de objetivos, metas e indicadores del PESV."}],
        _control("Objetivos y metas"),
    )

    assert result.document_type == "matriz"
    assert result.topic == "Seguridad vial"
    assert result.conflict_status == "none"
    assert result.conflicts == []


def test_convivencia_policy_keeps_convivencia_topic_from_route() -> None:
    result = classify_document(
        "convivencia_laboral/manual/politica_desconexion.pdf",
        [{"text_raw": "POLÍTICA DE DESCONEXIÓN LABORAL"}],
        _control("Política de desconexión laboral"),
    )

    assert result.document_type == "politica"
    assert result.topic == "Convivencia laboral"


def test_acoso_policy_keeps_convivencia_topic_from_title() -> None:
    result = classify_document(
        "convivencia_laboral/manual/politica_acoso.pdf",
        [{"text_raw": "POLÍTICA DE PREVENCIÓN DE ACOSO LABORAL"}],
        _control("Política de prevención de acoso laboral"),
    )

    assert result.document_type == "politica"
    assert result.topic == "Convivencia laboral"


def test_sst_policy_uses_sgsst_topic_from_explicit_title() -> None:
    result = classify_document(
        "general_sst/manuales/politica/politica.pdf",
        [{"text_raw": "POLÍTICA DE SEGURIDAD Y SALUD EN EL TRABAJO"}],
        _control("Política de seguridad y salud en el trabajo"),
    )

    assert result.document_type == "politica"
    assert result.topic == "Sistema de Gestión de Seguridad y Salud en el Trabajo"


def test_reglamento_del_comite_keeps_committee_operation_subtopic() -> None:
    result = classify_document(
        "convivencia_laboral/reglamento_comite/reglamento.pdf",
        [{"text_raw": "REGLAMENTO DEL COMITÉ DE CONVIVENCIA LABORAL"}],
        _control("Reglamento del Comité de Convivencia Laboral"),
    )

    assert result.document_type == "reglamento"
    assert result.subtopic == "Funcionamiento del comité"


def test_route_only_result_is_low_confidence() -> None:
    result = classify_document("sst/manuales/archivo.pdf", [{"text_raw": "contenido generico"}], _control("Documento"))
    assert result.document_type == "manual"
    assert result.document_type_confidence.value == 0.45
    assert "route_only_low_confidence" in result.warnings


def test_route_only_topic_result_is_low_confidence_and_warned() -> None:
    result = classify_document(
        "sst/auditoria/archivo.pdf",
        [{"text_raw": "contenido generico"}],
        _control("Documento"),
    )

    assert result.document_type == "otro"
    assert result.topic == "Auditoria"
    assert result.topic_confidence.value == 0.45
    assert "route_only_low_confidence" in result.warnings


def test_type_and_topic_have_independent_confidence() -> None:
    result = classify_document("sst/archivo.pdf", [{"text_raw": "# Procedimiento de auditoria"}], _control("Procedimiento de auditoria"))
    assert result.document_type == "procedimiento"
    assert result.topic == "Auditoria"
    assert result.document_type_confidence.value == 0.95
    assert result.topic_confidence.value == 0.95


def test_legacy_path_and_text_call_remains_supported() -> None:
    result = classify_document(Path("sst/formularios/FR-SST-01.md"), "# Formato de inspeccion")
    assert result["document_type"] == "formulario"
    assert result["topic"] == "Formularios"


@pytest.mark.parametrize(
    ("title", "expected_type"),
    [
        ("Manual operativo", "manual"),
        ("Formato de inspeccion", "formulario"),
        ("Politica SST", "politica"),
        ("Reglamento interno", "reglamento"),
        ("Programa anual", "programa"),
        ("Matriz de riesgos", "matriz"),
        ("Procedimiento de compras", "procedimiento"),
        ("Anexo tecnico", "anexo"),
        ("Instructivo de uso", "instructivo"),
        ("Capacitacion inicial", "capacitacion"),
        ("Acta de reunion", "acta"),
        ("Norma aplicable", "norma"),
        ("Guia de trabajo", "guia"),
        ("Comunicacion interna", "informacion_general"),
        ("Documento sin clasificar", "otro"),
    ],
)
def test_retains_every_schema_document_type(title: str, expected_type: str) -> None:
    result = classify_document("sst/archivo.pdf", [{"text_raw": f"# {title}"}], _control(title))
    assert result.document_type == expected_type
