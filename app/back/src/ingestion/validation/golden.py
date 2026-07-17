from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from ingestion.schemas.common import RelativePosixPath, StrictModel
from ingestion.schemas.artifacts import ValidationCheck, ValidationReport


class GoldenDocument(StrictModel):
    document_id: str
    source_relpath: RelativePosixPath
    page_count: int = Field(ge=1)
    expected: dict
    review_status: str


class GoldenCorpus(StrictModel):
    audit_schema_version: str
    documents: list[GoldenDocument]


def load_golden(path: Path, *, raw_root_name: str = "data/docs_raw") -> GoldenCorpus:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = []
    for item in payload.get("documents", []):
        item = dict(item)
        source_relpath = str(item["source_relpath"])
        prefix = raw_root_name.rstrip("/") + "/"
        if source_relpath.startswith(prefix):
            source_relpath = source_relpath[len(prefix) :]
        documents.append(
            GoldenDocument(
                document_id=item["document_id"],
                source_relpath=source_relpath,
                page_count=item["page_count"],
                expected=item.get("expected", {}),
                review_status=item["review_status"],
            )
        )
    return GoldenCorpus(
        audit_schema_version=str(payload.get("audit_schema_version", "")),
        documents=documents,
    )


def validate_pdf_corpus(candidate_root: Path, raw_root: Path, golden: GoldenCorpus) -> ValidationReport:
    checks: list[ValidationCheck] = []
    errors: list[str] = []
    seen_sources = set()
    for document in golden.documents:
        seen_sources.add(document.source_relpath)
        source = raw_root / document.source_relpath
        if not source.exists():
            errors.append(f"{document.source_relpath}: source missing")
        base = candidate_root / Path(document.source_relpath).with_suffix("")
        metadata_path = base.with_suffix(".metadata.json")
        pages_path = base.with_suffix(".pages.json")
        if not metadata_path.exists():
            errors.append(f"{document.source_relpath}: metadata missing")
        if not pages_path.exists():
            errors.append(f"{document.source_relpath}: pages missing")

    extras = [
        str(path.relative_to(candidate_root).with_suffix(".pdf"))
        for path in candidate_root.rglob("*.metadata.json")
        if str(path.relative_to(candidate_root).with_suffix(".pdf")) not in seen_sources
    ]
    checks.append(_check("golden_bijection", errors + [f"extra candidate: {extra}" for extra in extras]))
    checks.append(_check("golden_page_total", _page_total_errors(golden)))
    failed = sum(1 for check in checks if check.status == "failed")
    return ValidationReport(
        schema_version="2.0",
        run_id="golden",
        status="failed" if failed else "passed",
        documents_checked=len(golden.documents),
        errors=failed,
        checks=checks,
    )


def _page_total_errors(golden: GoldenCorpus) -> list[str]:
    total = sum(document.page_count for document in golden.documents)
    return [] if total == 77 else [f"expected 77 pages, got {total}"]


def _check(name: str, details: list[str]) -> ValidationCheck:
    return ValidationCheck(check=name, status="failed" if details else "passed", details=details)
