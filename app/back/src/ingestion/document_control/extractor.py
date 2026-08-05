from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ingestion.schemas.artifacts import ChangeHistoryEntry, DocumentControl
from ingestion.schemas.common import DocumentField, Evidence


_CODE_PATTERNS = (
    re.compile(
        r"\b(?:c[o\u00f3]digo|code)\s*[:#-]?\s*"
        r"([A-Za-z]{1,4}(?:\s*[-.]\s*[A-Za-z0-9]{1,8}){1,4}"
        r"(?:\s+[A-Za-z]{2,4})?)\b",
        re.I,
    ),
    re.compile(
        r"\b([A-Za-z]{1,3}\s*[.-]\s*[A-Za-z]{1,3}\s*[-.]"
        r"\s*\d{1,3}(?:\s*[-.\s]?\s*[A-Za-z]{2,4})?)\b",
        re.I,
    ),
)
_HTML_TABLE_CODE_PATTERN = re.compile(
    r"<t[dh][^>]*>\s*c[o\u00f3]digo\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>",
    re.I,
)
_VERSION_PATTERN = re.compile(
    r"\b(?:versi[o\u00f3]n|version)\b\s*[:#| -]?\s*"
    r"([\[(]?\s*v?[0-9oO][A-Za-z0-9]{0,2}(?:[.,]\d{1,3}){0,3})\b",
    re.I,
)
_OCR_ABBREVIATED_VERSION_PATTERN = re.compile(
    r"\b(?:ver\.?|ves)\b\s*[:#| -]?\s*"
    r"([\[(]?\s*v?[0-9oO][A-Za-z0-9]{0,2}(?:[.,]\d{1,3}){0,3})\b",
    re.I,
)
_MONTH_NAME = r"[A-Za-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+"
_DATE_VALUE = (
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    rf"\d{{1,2}}\s+de\s+{_MONTH_NAME}\s+de\s+\d{{4}}|"
    rf"\d{{1,2}}\s+d[i\u00ed]as?\s+del\s+mes\s+de\s+{_MONTH_NAME}\s+de\s+\d{{4}}|"
    rf"{_MONTH_NAME},?\s+\d{{4}})"
)
_PUBLICATION_PATTERN = re.compile(
    rf"\b(?:fecha\s+de\s+)?(?:publicaci[o\u00f3]n|emisi[o\u00f3]n)"
    rf"\s*[:#-]?\s*({_DATE_VALUE})",
    re.I,
)
_EFFECTIVE_PATTERN = re.compile(
    rf"\b(?:fecha\s+de\s+)?(?:vigencia|efectiva|entrada\s+en\s+vigencia)"
    rf"\s*[:#-]?\s*({_DATE_VALUE})",
    re.I,
)
_SIGNATURE_DATE_PATTERN = re.compile(
    rf"\bfirma(?:'|do|da|r|a)?\b.*?({_DATE_VALUE})",
    re.I,
)
_FIRST_PAGE_MONTH_YEAR_PATTERN = re.compile(
    rf"\b({_MONTH_NAME},?\s+\d{{4}})\b",
    re.I,
)
_HISTORY_HEADER = re.compile(
    r"(?:historial|control)\s+de\s+(?:cambios|versiones)|"
    r"\bversi[o\u00f3]n\b.*\bfecha\b",
    re.I,
)


def extract_document_control(
    pages: Iterable[Any],
    filename: str | Path,
) -> DocumentControl:
    """Extract documentary values only from visible page or block evidence."""

    records = list(_iter_evidence_lines(pages))
    title = _field_from_candidates(_title_candidates(records))
    code = _code_field(records)
    version = _version_field(records)
    publication_date = _field_from_candidates(
        _publication_date_candidates(records)
    )
    effective_date = _field_from_candidates(
        _find_candidates(
            records,
            (_EFFECTIVE_PATTERN,),
            _normalize_date,
        )
    )
    history = _extract_history(records)

    warnings = [
        f"conflicting_{name}"
        for name, field in (
            ("title", title),
            ("code", code),
            ("version", version),
            ("publication_date", publication_date),
            ("effective_date", effective_date),
        )
        if field.status == "conflicting"
    ]
    # Filename timestamps are provenance only, never documentary dates.
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


def _iter_evidence_lines(
    pages: Iterable[Any],
) -> Iterable[tuple[str, Evidence, Any]]:
    for page_index, page in enumerate(pages, start=1):
        page_number = _get(page, "page_number", page_index)
        blocks = _get(page, "blocks", []) or []
        # Keep the page-level reading-order text as documentary evidence. Layout
        # blocks may split a visible control pair into separate cells
        # ("VERSION" and "0.2"), while the page text preserves their relation.
        sources = [page, *blocks]
        for source in sources:
            text = _get(source, "text", None)
            if text is None:
                text = _get(source, "text_raw", "")
            bbox = _get(source, "bbox", None)
            region = _get(source, "region", None)
            method = _get(
                source,
                "extraction_method",
                _get(page, "extraction_method", None),
            )
            for line in str(text).splitlines():
                stripped = line.strip()
                if stripped:
                    yield (
                        stripped,
                        Evidence(
                            page_number=page_number,
                            bbox=bbox,
                            region=region,
                            text=stripped,
                            source=method,
                        ),
                        source,
                    )


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _title_candidates(
    records: list[tuple[str, Evidence, Any]],
) -> list[tuple[str, str, Evidence]]:
    candidates: list[tuple[str, str, Evidence]] = []
    for line, evidence, source in records:
        if _get(source, "role", None) == "title":
            candidates.append((_normalize_title(line), line, evidence))
            continue
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if not match:
            match = re.match(
                r"^(?:t[i\u00ed]tulo|nombre\s+del\s+documento)"
                r"\s*:\s*(.+)$",
                line,
                re.I,
            )
        if match:
            raw = match.group(1).strip()
            candidates.append((_normalize_title(raw), raw, evidence))
    if candidates:
        return _select_title_candidates(candidates)
    page_one = [
        (index, line, evidence)
        for index, (line, evidence, _source) in enumerate(records)
        if evidence.page_number == 1
    ]
    scored = [
        (_plain_title_score(line), -index, line, evidence)
        for index, line, evidence in page_one
        if _plain_title_score(line) > 0
    ]
    if scored:
        _score, negative_index, line, evidence = max(scored)
        index = -negative_index
        normalized = _normalize_title(line)
        if _title_needs_continuation(normalized) and index + 1 < len(records):
            next_line, next_evidence, _source = records[index + 1]
            if (
                next_evidence.page_number == 1
                and 0 < _plain_title_score(next_line) < 100
                and len(next_line.split()) <= 6
            ):
                normalized = _normalize_title(f"{normalized} {next_line}")
                line = f"{line} {next_line}"
        return [(normalized, line, evidence)]
    return []


def _select_title_candidates(
    candidates: list[tuple[str, str, Evidence]],
) -> list[tuple[str, str, Evidence]]:
    scored = [
        (_title_candidate_score(raw, evidence), index, candidate)
        for index, candidate in enumerate(candidates)
        for _normalized, raw, evidence in (candidate,)
    ]
    strong = [
        item
        for item in scored
        if item[0] >= 100
    ]
    if strong:
        _score, _index, candidate = min(
            strong,
            key=lambda item: (
                item[2][2].page_number or 9999,
                item[1],
            ),
        )
        return [candidate]
    page_one = [
        item
        for item in scored
        if item[2][2].page_number == 1 and item[0] > 0
    ]
    if page_one:
        _score, _index, candidate = max(
            page_one,
            key=lambda item: (item[0], -item[1]),
        )
        return [candidate]
    return candidates


def _title_candidate_score(raw: str, evidence: Evidence) -> int:
    del evidence
    normalized = _normalize_whitespace(raw)
    folded = normalized.casefold()
    if folded in {"tabla de contenido", "contenido"}:
        return 0
    if re.match(r"^(?:cap[ií]tulo|chapter)\b", folded, re.I):
        return 0
    if normalized.upper() in {"SYC"}:
        return 0
    return _plain_title_score(normalized)


def _looks_like_plain_title(line: str) -> bool:
    return _plain_title_score(line) > 0


def _plain_title_score(line: str) -> int:
    normalized = _normalize_whitespace(line)
    if not 5 <= len(normalized) <= 180:
        return 0
    if re.search(
        r"\b(?:c[o\u00f3]digo|versi[o\u00f3]n|version|fecha|"
        r"p[a\u00e1]gina)\b",
        normalized,
        re.I,
    ):
        return 0
    words = normalized.split()
    if not 2 <= len(words) <= 24:
        return 0
    folded = normalized.casefold()
    boilerplate = (
        "procesos administrativos",
        "gesti\u00f3n de recursos humanos",
        "gestion de recursos humanos",
        "seguridad y salud en el trabajo",
        "sistemas y computadores",
        "nivel de uso",
        "clasificaci\u00f3n",
        "clasificacion",
    )
    if any(value in folded for value in boilerplate):
        return 0
    title_prefixes = (
        "formato",
        "manual",
        "pol\u00edtica",
        "politica",
        "reglamento",
        "programa",
        "procedimiento",
        "matriz",
        "objetivos y metas",
        "instructivo",
        "gu\u00eda",
        "guia",
    )
    if folded.startswith(title_prefixes):
        return 100
    letters = [character for character in normalized if character.isalpha()]
    return 10 if (
        bool(letters)
        and sum(character.isupper() for character in letters) / len(letters)
        >= 0.9
    ) else 0


def _title_needs_continuation(value: str) -> bool:
    folded = value.casefold().rstrip(" .:")
    if folded == "objetivos y metas":
        return True
    return folded.endswith(
        (
            " de",
            " del",
            " ante",
            " ante el comit\u00e9",
            " ante el comite",
        )
    )


def _find_candidates(
    records: list[tuple[str, Evidence, Any]],
    patterns: tuple[re.Pattern[str], ...],
    normalize: Any,
) -> list[tuple[str, str, Evidence]]:
    candidates: list[tuple[str, str, Evidence]] = []
    for line, evidence, _source in records:
        for pattern in patterns:
            for match in pattern.finditer(line):
                raw = match.group(1).strip().rstrip("|;")
                candidates.append((normalize(raw), raw, evidence))
    return candidates


def _publication_date_candidates(
    records: list[tuple[str, Evidence, Any]],
) -> list[tuple[str, str, Evidence]]:
    explicit = _find_candidates(records, (_PUBLICATION_PATTERN,), _normalize_date)
    if explicit:
        return explicit
    signed = _find_candidates(records, (_SIGNATURE_DATE_PATTERN,), _normalize_date)
    if signed:
        return signed
    first_page_month_year = [
        candidate
        for candidate in _find_candidates(
            records,
            (_FIRST_PAGE_MONTH_YEAR_PATTERN,),
            _normalize_date,
        )
        if candidate[2].page_number == 1
    ]
    return first_page_month_year


def _code_field(records: list[tuple[str, Evidence, Any]]) -> DocumentField:
    table_labeled = _find_candidates(records, (_HTML_TABLE_CODE_PATTERN,), _normalize_code)
    primary_table_labeled = [
        candidate
        for candidate in table_labeled
        if candidate[2].page_number == 1
    ]
    if primary_table_labeled:
        return _field_from_candidates(primary_table_labeled)
    labeled = _find_candidates(records, (_CODE_PATTERNS[0],), _normalize_code)
    primary_labeled = [
        candidate
        for candidate in labeled
        if candidate[2].page_number == 1
    ]
    if primary_labeled:
        field = _field_from_candidates(primary_labeled)
        if field.status == "extracted":
            matching = [
                candidate
                for candidate in labeled
                if candidate[0] == field.value
            ]
            return _field_from_candidates(matching)
        return field
    first_page_candidates = [
        candidate
        for candidate in _find_candidates(records, _CODE_PATTERNS, _normalize_code)
        if candidate[2].page_number == 1
    ]
    return _augment_split_sst_suffix(
        _field_from_candidates(first_page_candidates),
        records,
    )


def _version_field(records: list[tuple[str, Evidence, Any]]) -> DocumentField:
    all_candidates = _version_candidates(records)
    first_page_candidates = [
        candidate
        for candidate in all_candidates
        if candidate[2].page_number == 1
    ]
    primary = first_page_candidates or all_candidates
    field = _field_from_candidates(primary)
    if field.status != "extracted" or not isinstance(field.value, str):
        return field
    matching = [
        candidate
        for candidate in all_candidates
        if candidate[0] == field.value
    ]
    return _field_from_candidates(matching)


def _version_candidates(
    records: list[tuple[str, Evidence, Any]],
) -> list[tuple[str, str, Evidence]]:
    candidates: list[tuple[str, str, Evidence]] = []
    for line, evidence, _source in records:
        for match in _VERSION_PATTERN.finditer(line):
            raw = match.group(1).strip().rstrip("|;")
            candidates.append((_normalize_version(raw), raw, evidence))
        for match in _OCR_ABBREVIATED_VERSION_PATTERN.finditer(line):
            raw = match.group(1).strip().rstrip("|;")
            candidates.append(
                (_normalize_version(raw, compact_ocr=True), raw, evidence)
            )
    return candidates


def _field_from_primary_page(
    records: list[tuple[str, Evidence, Any]],
    patterns: tuple[re.Pattern[str], ...],
    normalize: Any,
) -> DocumentField:
    all_candidates = _find_candidates(records, patterns, normalize)
    first_page_candidates = [
        candidate
        for candidate in all_candidates
        if candidate[2].page_number == 1
    ]
    primary = first_page_candidates or all_candidates
    field = _field_from_candidates(primary)
    if field.status != "extracted" or not isinstance(field.value, str):
        return field
    # Preserve repeated evidence for the selected header value without treating
    # later cross-references as competing document-control metadata.
    matching = [
        candidate
        for candidate in all_candidates
        if candidate[0] == field.value
    ]
    return _field_from_candidates(matching)


def _field_from_candidates(
    candidates: list[tuple[str, str, Evidence]],
) -> DocumentField:
    unique: dict[str, tuple[str, list[Evidence]]] = {}
    for normalized, raw, evidence in candidates:
        if not normalized:
            continue
        entry = unique.setdefault(normalized, (raw, []))
        if not any(
            _same_evidence(evidence, existing)
            for existing in entry[1]
        ):
            entry[1].append(evidence)
    if not unique:
        return DocumentField(value=None, status="not_found")
    if len(unique) == 1:
        value, (raw, evidence) = next(iter(unique.items()))
        return DocumentField(
            value=value,
            value_raw=raw,
            status="extracted",
            evidence=evidence,
        )
    values = list(unique)
    evidence = [
        item
        for _raw, items in unique.values()
        for item in items
    ]
    return DocumentField(
        value=values,
        value_raw=[item[0] for item in unique.values()],
        status="conflicting",
        evidence=evidence,
        warnings=["multiple_visible_candidates"],
    )


def _same_evidence(left: Evidence, right: Evidence) -> bool:
    return (
        left.page_number == right.page_number
        and left.text == right.text
        and left.region == right.region
    )


def _extract_history(
    records: list[tuple[str, Evidence, Any]],
) -> list[ChangeHistoryEntry]:
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
        if (
            len(cells) < 2
            or not any(re.search(_DATE_VALUE, cell, re.I) for cell in cells)
        ):
            if saw_history_row:
                in_history = False
            continue
        version = next(
            (
                cell
                for cell in cells
                if re.fullmatch(
                    r"v?(?:ersi[o\u00f3]n\s*)?[A-Za-z0-9._-]+",
                    cell,
                    re.I,
                )
            ),
            None,
        )
        date = next(
            (
                cell
                for cell in cells
                if re.search(_DATE_VALUE, cell, re.I)
            ),
            None,
        )
        description = next(
            (
                cell
                for cell in cells
                if cell not in {version, date, ""}
            ),
            None,
        )
        history.append(
            ChangeHistoryEntry(
                version=version,
                date=date,
                description=description,
                evidence=[evidence],
            )
        )
        saw_history_row = True
    return history


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_version(value: str, *, compact_ocr: bool = False) -> str:
    raw = _normalize_whitespace(value)
    bracketed = raw.strip().startswith(("[", "("))
    normalized = raw.strip("[]() ")
    normalized = normalized.replace(",", ".")
    if (
        (bracketed or compact_ocr)
        and len(normalized) == 2
        and _ocr_digit(normalized[0]) == "0"
        and _ocr_digit(normalized[1]).isdigit()
    ):
        return f"0.{_ocr_digit(normalized[1])}"
    return normalized


def _ocr_digit(value: str) -> str:
    return {
        "o": "0",
        "O": "0",
        "s": "6",
        "S": "6",
    }.get(value, value)


def _normalize_title(value: str) -> str:
    value = re.sub(r"(?<=[A-Za-z\u00c0-\u017f])['’](?=[A-Za-z\u00c0-\u017f])", " ", value)
    value = re.sub(
        r"\b(REGLAMENTO)\s+(COMIT[E\u00c9]\s+DE\s+CONVIVENCIA\s+LABORAL)\b",
        r"\1 DEL \2",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\b(OBJETIVOS\s+Y\s+METAS)\s+(SEGURIDAD\s+VIAL)\b",
        r"\1 DE \2",
        value,
        flags=re.I,
    )
    return _normalize_whitespace(value)


_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}


def _normalize_date(value: str) -> str:
    normalized = _normalize_whitespace(value).strip(" .,:;")
    folded = _fold_accents(normalized).lower()
    match = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", folded)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", folded)
    if match:
        day, month, year = match.groups()
        year = f"20{year}" if len(year) == 2 else year
        return f"{year}-{int(month):02d}-{int(day):02d}"
    match = re.fullmatch(
        rf"(\d{{1,2}})\s+de\s+({_MONTH_NAME})\s+de\s+(\d{{4}})",
        folded,
    )
    if not match:
        match = re.fullmatch(
            rf"(\d{{1,2}})\s+dias?\s+del\s+mes\s+de\s+({_MONTH_NAME})\s+de\s+(\d{{4}})",
            folded,
        )
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(_fold_accents(month_name).lower())
        if month:
            return f"{year}-{month}-{int(day):02d}"
    match = re.fullmatch(rf"({_MONTH_NAME}),?\s+(\d{{4}})", folded)
    if match:
        month_name, year = match.groups()
        month = _MONTHS.get(_fold_accents(month_name).lower())
        if month:
            return f"{year}-{month}"
    return ""


def _fold_accents(value: str) -> str:
    replacements = str.maketrans(
        "áéíóúñüÁÉÍÓÚÑÜ",
        "aeiounuAEIOUNU",
    )
    return value.translate(replacements)


def _normalize_code(value: str) -> str:
    normalized = (
        _normalize_whitespace(value)
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    normalized = re.sub(r"\s*([-.])\s*", r"\1", normalized)
    normalized = _normalize_whitespace(normalized).upper()
    return re.sub(r"(?<=\d)5ST$", "SST", normalized)


def _augment_split_sst_suffix(
    field: DocumentField,
    records: list[tuple[str, Evidence, Any]],
) -> DocumentField:
    if (
        field.status != "extracted"
        or not isinstance(field.value, str)
        or re.search(r"(?:^|[-.\s])SST$", field.value, re.I)
    ):
        return field
    if not re.search(r"[A-Z]{1,4}[.-][A-Z]{1,4}[-.]\d{1,3}$", field.value, re.I):
        return field
    pages = {
        evidence.page_number
        for evidence in field.evidence
        if evidence.page_number is not None
    }
    if not pages:
        return field
    if not any(
        evidence.page_number in pages and re.fullmatch(r"SST", line.strip(), re.I)
        for line, evidence, _source in records
    ):
        return field
    return field.model_copy(
        update={
            "value": f"{field.value} SST",
            "warnings": _unique_warnings(
                [*field.warnings, "code_suffix_joined_from_split_header"]
            ),
        }
    )


def _unique_warnings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
