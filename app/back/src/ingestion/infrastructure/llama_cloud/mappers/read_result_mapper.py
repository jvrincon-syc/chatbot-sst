from __future__ import annotations

import re
from html.parser import HTMLParser

from ingestion.domain.models.parsed_document import ParsedDocument
from ingestion.normalization.text import normalize_text
from ingestion.readers.base import ReadResult
from ingestion.schemas.artifacts import (
    FormGroup,
    FormLabel,
    FormsArtifact,
    PageRecord,
    TableCell,
    TableRecord,
    TablesArtifact,
)
from ingestion.schemas.common import ConfidenceMetric, Evidence, Observation


def parsed_document_to_read_result(parsed: ParsedDocument) -> ReadResult:
    pages = [
        PageRecord(
            page_number=page.page_number,
            text_raw=page.markdown,
            text_normalized=normalize_text(page.markdown),
            extraction_method="llamaparse",
            ocr_confidence=ConfidenceMetric(kind="unavailable", value=None),
            warnings=page.warnings,
        )
        for page in parsed.markdown_pages
    ]
    markdown = "\n\n".join(
        f"<!-- page: {page.page_number} -->\n\n{page.markdown}"
        for page in parsed.markdown_pages
    ).strip()
    return ReadResult(
        extraction_method="llamaparse",
        markdown=markdown,
        pages=pages,
        warnings=[f"llama_parse_job:{parsed.provider_job.job_id}", *parsed.warnings],
        review_reasons=[],
        tables=_tables_from_markdown_pages(parsed.provider_job.job_id, parsed.markdown_pages),
        forms=_forms_from_markdown_pages(parsed.provider_job.job_id, parsed.markdown_pages),
    )


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, bool]]]] = []
        self._current_table: list[list[tuple[str, bool]]] | None = None
        self._current_row: list[tuple[str, bool]] | None = None
        self._current_cell: list[str] | None = None
        self._current_is_header = False
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            if self._table_depth == 0:
                self._current_table = []
            self._table_depth += 1
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
            self._current_is_header = tag == "th"

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = normalize_text(" ".join(self._current_cell)).strip()
            self._current_row.append((text, self._current_is_header))
            self._current_cell = None
            self._current_is_header = False
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(text for text, _is_header in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._current_table is not None:
                if self._current_table:
                    self.tables.append(self._current_table)
                self._current_table = None


def _tables_from_markdown_pages(document_id: str, markdown_pages) -> TablesArtifact:
    records: list[TableRecord] = []
    observations: list[Observation] = []
    for page in markdown_pages:
        parser = _HtmlTableParser()
        parser.feed(page.markdown)
        if not parser.tables:
            observations.append(
                Observation(
                    status="not_detected",
                    value=False,
                    method="llamaparse_markdown_table",
                )
            )
            continue
        observations.append(
            Observation(
                status="detected",
                value=True,
                method="llamaparse_markdown_table",
                evidence=[
                    Evidence(
                        page_number=page.page_number,
                        source="llamaparse",
                        text="html_table",
                    )
                ],
            )
        )
        for table_index, table in enumerate(parser.tables, start=1):
            rows = [[text for text, _is_header in row] for row in table]
            headers = [
                text
                for text, is_header in table[0]
                if is_header and text
            ] if table else []
            cells = [
                TableCell(row_index=row_index, column_index=column_index, text=text)
                for row_index, row in enumerate(rows)
                for column_index, text in enumerate(row)
            ]
            records.append(
                TableRecord(
                    table_id=f"{document_id}_p{page.page_number}_table_{table_index:03d}",
                    page_number=page.page_number,
                    bbox=None,
                    headers=headers,
                    cells=cells,
                    rows=rows,
                    markdown_representation=_table_markdown(rows),
                    extractor="llamaparse_markdown_table",
                    quality=ConfidenceMetric(kind="unavailable", value=None),
                    warnings=[],
                )
            )
    return TablesArtifact(
        schema_version="2.0",
        document_id=document_id,
        table_count=len(records),
        tables=records,
        page_observations=observations,
    )


def _table_markdown(rows: list[list[str]]) -> str:
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def _forms_from_markdown_pages(document_id: str, markdown_pages) -> FormsArtifact:
    groups: list[FormGroup] = []
    observations: list[Observation] = []
    for page in markdown_pages:
        labels = _form_labels_from_markdown(page.markdown)
        if not labels:
            observations.append(
                Observation(
                    status="not_detected",
                    value=False,
                    method="llamaparse_form_heuristic",
                )
            )
            continue
        observations.append(
            Observation(
                status="detected",
                value=True,
                method="llamaparse_form_heuristic",
                evidence=[
                    Evidence(
                        page_number=page.page_number,
                        source="llamaparse",
                        text=", ".join(labels[:3]),
                    )
                ],
            )
        )
        groups.append(
            FormGroup(
                group_id=f"{document_id}_p{page.page_number}_form_001",
                page_number=page.page_number,
                title=None,
                labels=[
                    FormLabel(
                        label_id=f"{document_id}_p{page.page_number}_label_{index:03d}",
                        text=label,
                    )
                    for index, label in enumerate(labels, start=1)
                ],
                controls=[],
                warnings=["generated_from_llamaparse_markdown_form_cues"],
            )
        )
    return FormsArtifact(
        schema_version="2.0",
        document_id=document_id,
        groups=groups,
        page_observations=observations,
    )


def _form_labels_from_markdown(markdown: str) -> list[str]:
    labels: list[str] = []
    strong_form_cue = re.search(r"^\s*#{1,6}\s+.*\bformato\s+para\s+interponer\s+queja\b", markdown, re.I | re.M)
    blank_cue = re.search(r"_{4,}|\[\s?\]|\(\s?\)", markdown)
    label_cue = re.search(r"\b(nombre completo|identificaci[oó]n|firma del que interpone|sugerencias)\s*:", markdown, re.I)
    if not (strong_form_cue or blank_cue or label_cue):
        return []
    for line in markdown.splitlines():
        cleaned = normalize_text(re.sub(r"<[^>]+>", " ", line)).strip(" #|")
        match = re.match(r"^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 /().,-]{3,80})\s*:\s*(?:_{2,}|\s*$)", cleaned)
        if match:
            labels.append(match.group(1).strip())
    if labels and (blank_cue or label_cue or strong_form_cue):
        return list(dict.fromkeys(labels))
    if not strong_form_cue:
        return []
    cue_labels = []
    for pattern in (
        r"FIRMA(?:\s+DEL\s+QUE\s+INTERPONE\s+LA\s+QUEJA)?",
        r"NOMBRE\s+COMPLETO",
        r"RELACI[OÓ]N\s+DE\s+LOS\s+HECHOS",
        r"SUGERENCIAS",
        r"PRUEBAS",
    ):
        cue_labels.extend(match.group(0).upper() for match in re.finditer(pattern, markdown, re.I))
    return list(dict.fromkeys(cue_labels))
