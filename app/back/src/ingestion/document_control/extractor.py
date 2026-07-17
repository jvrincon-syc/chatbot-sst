from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ingestion.schemas.artifacts import ChangeHistoryEntry, DocumentControl
from ingestion.schemas.common import DocumentField, Evidence


_CODE_PATTERNS = (
    re.compile(r"\b(?:c[oó]digo|code)\s*[:#-]?\s*([A-Za-z]{1,8}(?:\s*[-.]\s*[A-Za-z0-9]{1,12}){1,5})", re.I),
    re.compile(r"\b([A-Za-z]{2,8}\s*[-.]\s*[A-Za-z0-9]{1,12}(?:\s*[-.]\s*[A-Za-z0-9]{1,12}){0,4})\b"),
)
_VERSION_PATTERN = re.compile(r"\b(?:versi[oó]n|version|ver\.)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9 ._-]{0,24})", re.I)
_DATE_VALUE = r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\s+de\s+[A-Za-záéíóúñ]+\s+de\s+\d{4})"
_PUBLICATION_PATTERN = re.compile(r"\b(?:fecha\s+de\s+)?(?:publicaci[oó]n|emisi[oó]n)\s*[:#-]?\s*(%s)" % _DATE_VALUE, re.I)
_EFFECTIVE_PATTERN = re.compile(r"\b(?:fecha\s+de\s+)?(?:vigencia|efectiva|entrada\s+en\s+vigencia)\s*[:#-]?\s*(%s)" % _DATE_VALUE, re.I)
_HISTORY_HEADER = re.compile(r"(?:historial|control)\s+de\s+(?:cambios|versiones)|\bversi[oó]n\b.*\bfecha\b", re.I)


def extract_document_control(pages: Iterable[Any], filename: str | Path) -> DocumentControl:
    """Extract only documentary values that are visibly present in page text/blocks."""

    records = list(_iter_evidence_lines(pages))
    title = _field_from_candidates(_title_candidates(records))
    code = _field_from_candidates(_find_candidates(records, _CODE_PATTERNS, _normalize_code))
    version = _field_from_candidates(_find_candidates(records, (_VERSION_PATTERN,), _normalize_whitespace))
    publication_date = _field_from_candidates(
        _find_candidates(records, (_PUBLICATION_PATTERN,), _normalize_whitespace)
    )
    effective_date = _field_from_candidates(
        _find_candidates(records, (_EFFECTIVE_PATTERN,), _normalize_whitespace)
    )
    history = _extract_history(records)

    warnings: list[str] = []
    for name, field in (("title", title), ("code", code), ("version", version), ("publication_date", publication_date), ("effective_date", effective_date)):
        if field.status == "conflicting":
            warnings.append(f"conflicting_{name}")
    # The filename is deliberately not parsed: timestamp-like names are provenance, not dates.
    del filename
    return DocumentControl(
        title=title,
        code=code,
        version=version,
        publication_date=publication_date,
        effective_date=effective_date,
        change_history=history,
        warnings=warnings,
    )


def _iter_evidence_lines(pages: Iterable[Any]) -> Iterable[tuple[str, Evidence, Any]]:
    for page_index, page in enumerate(pages, start=1):
        page_number = _get(page, "page_number", page_index)
        blocks = _get(page, "blocks", []) or []
        sources = blocks or [page]
        for source in sources:
            text = _get(source, "text", None)
            if text is None:
                text = _get(source, "text_raw", "")
            bbox = _get(source, "bbox", None)
            region = _get(source, "region", None)
            method = _get(source, "extraction_method", _get(page, "extraction_method", None))
            for line in str(text).splitlines():
                stripped = line.strip()
                if stripped:
                    yield stripped, Evidence(page_number=page_number, bbox=bbox, region=region, text=stripped, source=method), source


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _title_candidates(records: list[tuple[str, Evidence, Any]]) -> list[tuple[str, str, Evidence]]:
    candidates: list[tuple[str, str, Evidence]] = []
    for line, evidence, source in records:
        if _get(source, "role", None) == "title":
            candidates.append((_normalize_whitespace(line), line, evidence))
            continue
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if not match:
            match = re.match(r"^(?:t[ií]tulo|nombre\s+del\s+documento)\s*:\s*(.+)$", line, re.I)
        if match:
            raw = match.group(1).strip()
            candidates.append((_normalize_whitespace(raw), raw, evidence))
    return candidates


def _find_candidates(records: list[tuple[str, Evidence, Any]], patterns: tuple[re.Pattern[str], ...], normalize: Any) -> list[tuple[str, str, Evidence]]:
    candidates: list[tuple[str, str, Evidence]] = []
    for line, evidence, _source in records:
        for pattern in patterns:
            for match in pattern.finditer(line):
                raw = match.group(1).strip().rstrip("|;")
                candidates.append((normalize(raw), raw, evidence))
    return candidates


def _field_from_candidates(candidates: list[tuple[str, str, Evidence]]) -> DocumentField:
    unique: dict[str, tuple[str, list[Evidence]]] = {}
    for normalized, raw, evidence in candidates:
        if not normalized:
            continue
        entry = unique.setdefault(normalized, (raw, []))
        if not any(_same_evidence(evidence, existing) for existing in entry[1]):
            entry[1].append(evidence)
    if not unique:
        return DocumentField(value=None, status="not_found")
    if len(unique) == 1:
        value, (raw, evidence) = next(iter(unique.items()))
        return DocumentField(value=value, value_raw=raw, status="extracted", evidence=evidence)
    values = list(unique)
    evidence = [item for _raw, items in unique.values() for item in items]
    return DocumentField(value=values, value_raw=[item[0] for item in unique.values()], status="conflicting", evidence=evidence, warnings=["multiple_visible_candidates"])


def _same_evidence(left: Evidence, right: Evidence) -> bool:
    return left.page_number == right.page_number and left.text == right.text and left.region == right.region


def _extract_history(records: list[tuple[str, Evidence, Any]]) -> list[ChangeHistoryEntry]:
    history: list[ChangeHistoryEntry] = []
    in_history = False
    saw_history_row = False
    for line, evidence, _source in records:
        if _HISTORY_HEADER.search(line):
            in_history = True
            saw_history_row = False
            continue
        if not in_history:
            continue
        if not line.startswith("|"):
            if saw_history_row or line.startswith("#"):
                in_history = False
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or not any(re.search(_DATE_VALUE, cell, re.I) for cell in cells):
            if saw_history_row:
                in_history = False
            continue
        version = next((cell for cell in cells if re.fullmatch(r"v?(?:ersi[oó]n\s*)?[A-Za-z0-9._-]+", cell, re.I)), None)
        date = next((cell for cell in cells if re.search(_DATE_VALUE, cell, re.I)), None)
        description = next((cell for cell in cells if cell not in {version, date, ""}), None)
        history.append(ChangeHistoryEntry(version=version, date=date, description=description, evidence=[evidence]))
        saw_history_row = True
    return history


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_code(value: str) -> str:
    return re.sub(r"\s*[-.]\s*", "-", _normalize_whitespace(value).replace("–", "-").replace("—", "-")).upper()
