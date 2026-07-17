from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple


TOPIC_RULES: List[Tuple[str, str]] = [
    ("copasst", "COPASST"),
    ("comite paritario", "COPASST"),
    ("convivencia laboral", "Comite de Convivencia Laboral"),
    ("convivencia", "Comite de Convivencia Laboral"),
    ("comite de convivencia", "Comite de Convivencia Laboral"),
    ("general sst", "SST"),
    ("sgsst", "SST"),
    ("reglamento interno", "Reglamento interno de trabajo"),
    ("seguridad vial", "Seguridad vial"),
    ("seguridad_vial", "Seguridad vial"),
    ("pausas activas", "Pausas activas"),
    ("pausas", "Pausas activas"),
    ("alcohol", "Prevencion de alcohol y drogas"),
    ("drogas", "Prevencion de alcohol y drogas"),
    ("auditoria", "Auditoria"),
    ("mejora", "Mejora"),
    ("planificacion", "Planificacion"),
    ("verificacion", "Verificacion"),
    ("organizacion", "Organizacion"),
    ("arl", "ARL"),
    ("formulario", "Formularios"),
    ("formato", "Formularios"),
    ("fr-sst", "Formularios"),
    ("capacitacion", "Capacitaciones"),
    ("capacitaciones", "Capacitaciones"),
    ("politica", "Politica de seguridad"),
]

TYPE_RULES: List[Tuple[str, str]] = [
    ("procedimiento", "procedimiento"),
    ("reglamento", "reglamento"),
    ("politica", "politica"),
    ("formato", "formulario"),
    ("formulario", "formulario"),
    ("fr-sst", "formulario"),
    ("anexo", "anexo"),
    ("instructivo", "instructivo"),
    ("capacitacion", "capacitacion"),
    ("acta", "acta"),
    ("norma", "norma"),
    ("guia", "guia"),
    ("comunicacion", "informacion_general"),
    ("miembros", "informacion_general"),
    ("valores", "informacion_general"),
    ("introduccion", "informacion_general"),
    ("aplicacion", "informacion_general"),
    ("manual", "manual"),
]


def classify_document(path: Path, text: str = "") -> dict:
    path_text = _normalize(path.as_posix())
    file_text = _normalize(path.name)
    heading_text = _normalize(_first_heading(text))
    sample_text = _normalize(text[:1000])
    haystacks = [
        ("heading", heading_text, 0.35),
        ("file_name", file_text, 0.30),
        ("path", path_text, 0.35),
        ("content", sample_text, 0.15),
    ]

    type_result = _score_rules(TYPE_RULES, haystacks)
    topic_result = _score_rules(TOPIC_RULES, haystacks)

    document_type = type_result["value"] or "otro"
    topic = topic_result["value"] or "SST"
    confidence = max(0.45, min(0.98, type_result["confidence"] + topic_result["confidence"]))
    reasons = type_result["reasons"] + topic_result["reasons"]

    if document_type == "formulario" and topic == "SST":
        topic = "Formularios"
        confidence = max(confidence, 0.80)
        reasons.append("topic_inferred_from_form_type")

    return {
        "document_type": document_type,
        "topic": topic,
        "classification_confidence": round(confidence, 2),
        "reasons": reasons,
    }


def _score_rules(rules: List[Tuple[str, str]], haystacks: List[Tuple[str, str, float]]) -> Dict:
    best = {"value": None, "confidence": 0.0, "reasons": []}
    for token, value in rules:
        token_norm = _normalize(token)
        matched_sources = [source for source, haystack, _weight in haystacks if token_norm and token_norm in haystack]
        if not matched_sources:
            continue
        confidence = sum(weight for source, haystack, weight in haystacks if token_norm in haystack)
        if confidence > best["confidence"]:
            best = {
                "value": value,
                "confidence": confidence,
                "reasons": [f"{value}:{token}:{source}" for source in matched_sources],
            }
    return best


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _normalize(value: str) -> str:
    accents = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return value.translate(accents).replace("_", " ").replace("-", "-").lower()
