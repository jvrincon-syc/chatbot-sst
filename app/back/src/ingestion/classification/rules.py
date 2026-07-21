from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, overload

from ingestion.schemas.artifacts import Classification, DocumentControl
from ingestion.schemas.common import ConfidenceMetric, DocumentField

ClassificationResult = Classification

_TYPE_RULES = (
    ("formulario", ("formato", "formulario", "fr-sst")),
    ("programa", ("programa",)),
    ("matriz", ("matriz", "objetivos y metas")),
    ("procedimiento", ("procedimiento",)),
    ("reglamento", ("reglamento",)),
    ("politica", ("politica",)),
    ("manual", ("manual",)),
    ("anexo", ("anexo",)),
    ("instructivo", ("instructivo",)),
    ("capacitacion", ("capacitacion",)),
    ("acta", ("acta",)),
    ("norma", ("norma",)),
    ("guia", ("guia",)),
    (
        "informacion_general",
        (
            "comunicacion",
            "miembros",
            "valores",
            "introduccion",
            "aplicacion",
            "funciones",
            "objetivo",
        ),
    ),
)

_TOPIC_RULES = (
    (
        "Sistema de Gestión de Seguridad y Salud en el Trabajo",
        (
            "seguridad y salud en el trabajo",
            "sistema de gestion de seguridad y salud",
            "sg-sst",
            "sgsst",
        ),
    ),
    ("COPASST", ("copasst", "comite paritario")),
    ("Comité de Convivencia Laboral", ("comite de convivencia",)),
    (
        "Convivencia laboral",
        (
            "convivencia laboral",
            "convivencia",
            "desconexion laboral",
            "acoso laboral",
        ),
    ),
    ("Política de seguridad", ("politica de seguridad",)),
    ("Seguridad vial", ("seguridad vial",)),
    ("Capacitaciones", ("capacitacion",)),
    ("Formularios", ("formulario", "formato", "fr-sst")),
    ("Reglamento interno de trabajo", ("reglamento interno",)),
    ("Pausas activas", ("pausas activas",)),
    ("Prevención de alcohol y drogas", ("alcohol", "drogas")),
    ("Auditoria", ("auditoria",)),
    ("Mejora", ("mejora",)),
    ("Planificacion", ("planificacion",)),
    ("Verificacion", ("verificacion",)),
    ("Organizacion", ("organizacion",)),
    ("ARL", ("arl",)),
)
_SUBTOPIC_RULES = (
    (
        "Queja por presunto acoso laboral",
        ("interponer queja", "presunto acoso"),
    ),
    (
        "Funcionamiento del comité",
        (
            "reglamento comite",
            "reglamento del comite",
            "funcionamiento del comite",
        ),
    ),
    (
        "Prevención de fatiga y desórdenes musculoesqueléticos",
        ("pausas activas", "fatiga", "musculoesquelet"),
    ),
    (
        "Objetivos, metas e indicadores",
        ("objetivos y metas", "metas e indicadores"),
    ),
    ("Desconexión laboral", ("desconexion laboral",)),
    (
        "Prevención del acoso laboral, sexual, violencia basada en género y discriminación",
        ("prevencion de acoso", "violencia basada en genero"),
    ),
    ("Política de SST", ("politica de seguridad y salud",)),
)
_AUTHORITY = {
    "title_control": 0.95,
    "content": 0.78,
    "filename": 0.65,
    "route": 0.45,
}


@overload
def classify_document(source_relpath: str, pages: Iterable[Any], document_control: DocumentControl) -> ClassificationResult: ...


@overload
def classify_document(source_relpath: Path, pages: str = "", document_control: None = None) -> dict[str, Any]: ...


def classify_document(
    source_relpath: str | Path,
    pages: Iterable[Any] | str = (),
    document_control: DocumentControl | None = None,
) -> ClassificationResult | dict[str, Any]:
    """Classify from strongest documentary evidence, with a narrow legacy adapter."""
    if document_control is None and isinstance(source_relpath, Path):
        return _classify_legacy(source_relpath, str(pages))
    if document_control is None:
        raise TypeError("document_control is required for the schema 2.0 classification interface")

    source = str(source_relpath)
    title = _field_text(document_control.title)
    control = " ".join(filter(None, (title, _field_text(document_control.code))))
    page_text = "\n".join(_page_text(page) for page in pages)
    filename = Path(source).name
    route = str(Path(source).parent)
    sources = (
        ("title_control", control),
        ("content", page_text),
        ("filename", filename),
        ("route", route),
    )
    type_choice, type_signals = _choose(_TYPE_RULES, sources)
    topic_choice, topic_signals = _choose(_TOPIC_RULES, sources)
    subtopic_choice, subtopic_signals = _choose(
        _SUBTOPIC_RULES,
        (("title_control", control),),
    )

    type_value, type_source = type_choice or ("otro", None)
    topic_value, topic_source = topic_choice or ("SST", None)
    subtopic_value = subtopic_choice[0] if subtopic_choice else None
    conflicts: list[str] = []
    return ClassificationResult(
        document_type=type_value,
        document_type_confidence=_confidence(type_source),
        topic=topic_value,
        subtopic=subtopic_value,
        topic_confidence=_confidence(topic_source),
        signals=type_signals + topic_signals + subtopic_signals,
        route_prior=_route_prior(route),
        content_prediction=_first_prediction(_TYPE_RULES, page_text),
        conflict_status="conflicting" if conflicts else "none",
        conflicts=conflicts,
        warnings=(
            ["route_only_low_confidence"]
            if type_source == "route" or topic_source == "route"
            else []
        ),
    )


def _classify_legacy(path: Path, text: str) -> dict[str, Any]:
    title = next(
        (
            line.lstrip("#").strip()
            for line in text.splitlines()
            if line.lstrip().startswith("#")
        ),
        "",
    )
    control = DocumentControl(
        title=(
            DocumentField(value=title, value_raw=title, status="extracted")
            if title
            else DocumentField(value=None, status="not_found")
        ),
        code=DocumentField(value=None, status="not_found"),
        version=DocumentField(value=None, status="not_found"),
        publication_date=DocumentField(value=None, status="not_found"),
        effective_date=DocumentField(value=None, status="not_found"),
    )
    result = classify_document(path.as_posix(), [{"text_raw": text}], control)
    confidence = max(result.document_type_confidence.value or 0, result.topic_confidence.value or 0)
    return {
        "document_type": result.document_type,
        "topic": result.topic,
        "classification_confidence": round(confidence, 2),
        "reasons": result.signals,
    }


def _choose(
    rules: tuple[tuple[str, tuple[str, ...]], ...],
    sources: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str] | None, list[str]]:
    matches: list[tuple[float, int, str, str, str]] = []
    for source, text in sources:
        normalized = _normalize(text)
        for rule_index, (value, tokens) in enumerate(rules):
            token = next((item for item in tokens if _normalize(item) in normalized), None)
            if token:
                matches.append(
                    (_AUTHORITY[source], rule_index, value, source, token)
                )
    if not matches:
        return None, []
    matches.sort(key=lambda item: (-item[0], item[1]))
    best = matches[0]
    return (best[2], best[3]), [
        f"{value}:{token}:{source}"
        for _score, _rule_index, value, source, token in matches
        if value == best[2] or source == "title_control"
    ]


def _confidence(source: str | None) -> ConfidenceMetric:
    return ConfidenceMetric(kind="estimated", value=_AUTHORITY.get(source, 0.35), method="evidence_precedence")


def _conflicts(
    rules: tuple[tuple[str, tuple[str, ...]], ...],
    control: str,
    route: str,
    label: str,
) -> list[str]:
    title_value = _first_prediction(rules, control)
    route_value = _first_prediction(rules, route)
    if title_value and route_value and title_value != route_value:
        return [f"{label}_title_control={title_value};{label}_route={route_value}"]
    return []


def _first_prediction(rules: tuple[tuple[str, tuple[str, ...]], ...], text: str) -> str | None:
    normalized = _normalize(text)
    return next((value for value, tokens in rules if any(_normalize(token) in normalized for token in tokens)), None)


def _page_text(page: Any) -> str:
    if isinstance(page, Mapping):
        return str(page.get("text_raw", page.get("text_normalized", page.get("text", ""))))
    return str(
        getattr(page, "text_raw", getattr(page, "text_normalized", getattr(page, "text", "")))
    )


def _field_text(field: DocumentField) -> str:
    return field.value if isinstance(field.value, str) else ""


def _route_prior(route: str) -> str | None:
    return _first_prediction(_TYPE_RULES, route)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_accents.replace("_", " ").replace("-", " ").split())
