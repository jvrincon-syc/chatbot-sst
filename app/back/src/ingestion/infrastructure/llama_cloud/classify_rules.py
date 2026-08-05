from __future__ import annotations


def classification_labels() -> dict[str, list[str]]:
    return {
        "manual": ["Documento instructivo o manual corporativo SST."],
        "formulario": ["Formato, formulario o plantilla con campos diligenciables."],
        "politica": ["Politica corporativa o declaracion formal."],
        "reglamento": ["Reglamento interno, comite o reglas operativas."],
        "programa": ["Programa SST, capacitacion o plan de actividades."],
        "matriz": ["Matriz de riesgos, objetivos, metas o indicadores."],
        "procedimiento": ["Procedimiento documentado con pasos de ejecucion."],
        "anexo": ["Anexo complementario a otro documento."],
        "instructivo": ["Instructivo especifico de uso o actividad."],
        "capacitacion": ["Material de capacitacion o sensibilizacion."],
        "acta": ["Acta de reunion, comite o decision."],
        "norma": ["Norma legal o tecnica aplicable."],
        "guia": ["Guia de referencia o consulta."],
        "informacion_general": ["Comunicacion, listado o informacion general."],
        "otro": ["Documento que no encaja con las categorias anteriores."],
    }


def topic_classification_labels() -> dict[str, list[str]]:
    return {
        "sg_sst": ["Sistema de gestion de seguridad y salud en el trabajo, politicas SST o documentos generales del SG-SST."],
        "copasst": ["Comite paritario de seguridad y salud en el trabajo, actas o reglas COPASST."],
        "comite_convivencia_laboral": ["Comite de convivencia laboral, quejas por acoso laboral o funcionamiento del comite."],
        "convivencia_laboral": ["Convivencia laboral, desconexion laboral, acoso laboral y politicas relacionadas."],
        "seguridad_vial": ["Seguridad vial, objetivos, metas, indicadores o planes viales."],
        "pausas_activas": ["Pausas activas, fatiga o desordenes musculoesqueleticos."],
        "reglamento_interno_trabajo": ["Reglamento interno de trabajo y reglas laborales operativas."],
        "capacitaciones": ["Capacitaciones, entrenamientos, sensibilizaciones o formacion SST."],
        "formularios": ["Formatos, formularios o registros diligenciables."],
        "sst_general": ["Tema SST general cuando no hay un topico especifico mas fuerte."],
    }


def canonical_topic(label: str) -> str:
    return {
        "sg_sst": "Sistema de Gestión de Seguridad y Salud en el Trabajo",
        "copasst": "COPASST",
        "comite_convivencia_laboral": "Comité de Convivencia Laboral",
        "convivencia_laboral": "Convivencia laboral",
        "seguridad_vial": "Seguridad vial",
        "pausas_activas": "Pausas activas",
        "reglamento_interno_trabajo": "Reglamento interno de trabajo",
        "capacitaciones": "Capacitaciones",
        "formularios": "Formularios",
        "sst_general": "SST",
    }.get(label, label)


def extraction_schema_for_document_type(document_type: str | None) -> str:
    if not document_type:
        return "document_control"
    if document_type == "formulario":
        return "formulario_document_control"
    if document_type in {"reglamento", "manual", "programa", "politica", "matriz"}:
        return f"{document_type}_document_control"
    return "document_control"
