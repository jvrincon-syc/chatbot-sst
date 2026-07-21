from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ingestion.schemas.artifacts import TableCell, TableRecord, TablesArtifact
from ingestion.schemas.common import BBox, ConfidenceMetric, Evidence, Observation


@dataclass
class TableExtractionResult:
    page_number: int
    tables: list[TableRecord] = field(default_factory=list)
    observation: Observation | None = None
    warnings: list[str] = field(default_factory=list)


class TableExtractor:
    def __init__(self, *, backend_available: bool = True, method: str = "pdfplumber") -> None:
        self.backend_available = backend_available
        self.method = method

    def evaluate(self, page: Any) -> TableExtractionResult:
        page_number = _page_number(page)
        if not self.backend_available:
            return TableExtractionResult(
                page_number=page_number,
                observation=Observation(
                    status="not_evaluated",
                    value=None,
                    method=self.method,
                    warnings=["table_extractor_unavailable"],
                ),
                warnings=["table_extractor_unavailable"],
            )

        tables = [
            _to_table_record(candidate, page_number, index, self.method)
            for index, candidate in enumerate(_table_candidates(page), start=1)
        ]
        tables = [table for table in tables if table is not None]
        if not tables:
            return TableExtractionResult(
                page_number=page_number,
                observation=Observation(status="not_detected", value=False, method=self.method),
            )

        evidence = [
            Evidence(page_number=page_number, bbox=table.bbox, source=self.method)
            for table in tables
            if table.bbox is not None
        ]
        if not evidence:
            evidence = [Evidence(page_number=page_number, source=self.method)]
        return TableExtractionResult(
            page_number=page_number,
            tables=tables,
            observation=Observation(
                status="detected",
                value=True,
                method=self.method,
                evidence=evidence,
            ),
        )

    def evaluate_pages(self, pages: Iterable[Any], *, document_id: str = "pending") -> TablesArtifact:
        results = [self.evaluate(page) for page in pages]
        tables = [table for result in results for table in result.tables]
        observations = [result.observation for result in results if result.observation is not None]
        warnings = sorted({warning for result in results for warning in result.warnings})
        return TablesArtifact(
            schema_version="2.0",
            document_id=document_id,
            table_count=len(tables),
            tables=tables,
            page_observations=observations,
            warnings=warnings,
        )


def _page_number(page: Any) -> int:
    return int(getattr(page, "page_number", 0) or 0)


def _table_candidates(page: Any) -> list[Any]:
    direct = getattr(page, "tables", None)
    if direct:
        return list(direct)
    finder = getattr(page, "find_tables", None)
    if callable(finder):
        return list(finder() or [])
    return _text_table_candidates(page)


def _text_table_candidates(page: Any) -> list[dict[str, Any]]:
    page_text = str(
        getattr(
            page,
            "text",
            getattr(page, "text_normalized", getattr(page, "text_raw", "")),
        )
        or ""
    )
    rows: list[list[str]] = []
    tables: list[dict[str, Any]] = []
    for line in page_text.splitlines():
        row = _pipe_row(line)
        if row is None:
            if rows:
                tables.append({"rows": rows})
                rows = []
            continue
        rows.append(row)
    if rows:
        tables.append({"rows": rows})
    return tables


def _pipe_row(line: str) -> list[str] | None:
    if "|" not in line:
        return None
    cells = [
        cell.strip(" \t|«»'\"")
        for cell in line.split("|")
    ]
    cells = [cell for cell in cells if cell]
    return cells if len(cells) >= 2 else None


def _to_table_record(candidate: Any, page_number: int, index: int, method: str) -> TableRecord | None:
    if isinstance(candidate, TableRecord):
        return candidate
    rows = _rows(candidate)
    if not rows:
        return None
    bbox = _bbox(getattr(candidate, "bbox", None) if not isinstance(candidate, dict) else candidate.get("bbox"))
    cells = _cells(candidate, rows, bbox)
    headers = [cell.strip() for cell in rows[0] if cell.strip()] if rows else []
    return TableRecord(
        table_id=f"page_{page_number}_table_{index}",
        page_number=page_number,
        bbox=bbox,
        headers=headers,
        cells=cells,
        rows=rows,
        markdown_representation=_markdown(rows),
        extractor=method,
        quality=_quality_metric(candidate, method),
    )


def _rows(candidate: Any) -> list[list[str]]:
    if isinstance(candidate, dict):
        rows = candidate.get("rows") or candidate.get("data")
    else:
        rows = getattr(candidate, "rows", None)
        if rows is None and callable(getattr(candidate, "extract", None)):
            rows = candidate.extract()
    return [[str(cell or "").strip() for cell in row] for row in (rows or [])]


def _cells(candidate: Any, rows: list[list[str]], table_bbox: BBox | None) -> list[TableCell]:
    raw_cells = candidate.get("cells") if isinstance(candidate, dict) else getattr(candidate, "cells", None)
    if raw_cells:
        cells: list[TableCell] = []
        for raw in raw_cells:
            if isinstance(raw, TableCell):
                cells.append(raw)
                continue
            getter = raw.get if isinstance(raw, dict) else lambda key, default=None: getattr(raw, key, default)
            cells.append(
                TableCell(
                    row_index=int(getter("row_index", getter("row", 0))),
                    column_index=int(getter("column_index", getter("column", 0))),
                    text=str(getter("text", "") or ""),
                    row_span=int(getter("row_span", 1) or 1),
                    column_span=int(getter("column_span", 1) or 1),
                    bbox=_bbox(getter("bbox", None)),
                )
            )
        return cells
    return [
        TableCell(
            row_index=row_index,
            column_index=column_index,
            text=text,
            bbox=table_bbox,
        )
        for row_index, row in enumerate(rows)
        for column_index, text in enumerate(row)
    ]


def _bbox(value: Any) -> BBox | None:
    if value is None:
        return None
    if isinstance(value, BBox):
        return value
    if isinstance(value, dict):
        return BBox(**value)
    if isinstance(value, (tuple, list)) and len(value) == 4:
        x0, top, x1, bottom = value
        return BBox(x0=x0, top=top, x1=x1, bottom=bottom, coordinate_system="pdf_points")
    return None


def _quality_metric(candidate: Any, method: str) -> ConfidenceMetric:
    raw = candidate.get("quality") if isinstance(candidate, dict) else getattr(candidate, "quality", None)
    if raw is None or isinstance(raw, bool):
        return ConfidenceMetric(kind="unavailable", value=None)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return ConfidenceMetric(kind="unavailable", value=None)
    if value < 0 or value > 1:
        return ConfidenceMetric(kind="unavailable", value=None)
    return ConfidenceMetric(
        kind="estimated",
        value=value,
        method=f"{method}_reported_table_quality",
        warnings=["table_quality_not_independently_measured"],
    )


def _markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    separator = ["---"] * len(header)
    body = rows[1:]
    markdown_rows = [header, separator, *body]
    return "\n".join("| " + " | ".join(row) + " |" for row in markdown_rows)
