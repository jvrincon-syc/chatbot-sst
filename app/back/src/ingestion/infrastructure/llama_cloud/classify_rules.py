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
