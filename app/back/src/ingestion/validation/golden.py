from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from ingestion.paths import ArtifactPaths
from ingestion.schemas.artifacts import (
    MetadataArtifact,
    PagesArtifact,
    ValidationCheck,
    ValidationReport,
)
from ingestion.schemas.common import RelativePosixPath, StrictModel
from ingestion.schemas.loader import load_artifact


ObservationStatus = Literal["detected", "not_detected", "not_evaluated"]


class GoldenExpected(StrictModel):
    title: str | None = None
    document_type: str | None = None
    topic: str | None = None
    subtopic: str | None = None
    document_code: str | None = None
    version: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None
    extraction_method: str | None = None
    contains_tables: ObservationStatus | None = None
    contains_form: ObservationStatus | None = None
    contains_handwriting: ObservationStatus | None = None
    version_status: str | None = None


class GoldenContentExpectation(StrictModel):
    pages: str
    must_preserve: list[str] = Field(default_factory=list)
    structure: str

    @field_validator("must_preserve")
    @classmethod
    def reject_descriptive_anchors(cls, values: list[str]) -> list[str]:
        descriptive_markers = (
            " row",
            " column",
            " should ",
            " must ",
            " contains ",
            " preserve ",
            " visible ",
            " flattened",
        )
        for value in values:
            normalized = f" {_normalized(value)} "
            if any(marker in normalized for marker in descriptive_markers):
                raise ValueError(
                    "must_preserve entries must be literal source anchors; "
                    f"move descriptive prose to structure: {value}"
                )
        return values


class GoldenDocument(StrictModel):
    document_id: str
    source_relpath: RelativePosixPath
    page_count: int = Field(ge=1)
    expected: GoldenExpected = Field(default_factory=GoldenExpected)
    minimum_content: list[GoldenContentExpectation] = Field(default_factory=list)
    known_current_defects: list[str] = Field(default_factory=list)
    review_status: str


class GoldenCorpus(StrictModel):
    audit_schema_version: str
    documents: list[GoldenDocument]


def load_golden(
    path: Path,
    *,
    raw_root_name: str = "data/docs_raw",
) -> GoldenCorpus:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = []
    for raw_item in payload.get("documents", []):
        item = dict(raw_item)
        source_relpath = str(item["source_relpath"])
        prefix = raw_root_name.rstrip("/") + "/"
        if source_relpath.startswith(prefix):
            source_relpath = source_relpath[len(prefix) :]
        documents.append(
            GoldenDocument(
                document_id=item["document_id"],
                source_relpath=source_relpath,
                page_count=item["page_count"],
                expected=GoldenExpected.model_validate(item.get("expected", {})),
                minimum_content=[
                    GoldenContentExpectation.model_validate(expectation)
                    for expectation in item.get("minimum_content", [])
                ],
                known_current_defects=item.get("known_current_defects", []),
                review_status=item["review_status"],
            )
        )
    return GoldenCorpus(
        audit_schema_version=str(payload.get("audit_schema_version", "")),
        documents=documents,
    )


def validate_pdf_corpus(
    candidate_root: Path,
    raw_root: Path,
    golden: GoldenCorpus,
) -> ValidationReport:
    candidate_root = Path(candidate_root)
    raw_root = Path(raw_root)
    bijection_errors: list[str] = []
    metadata_errors: list[str] = []
    page_errors: list[str] = []
    content_errors: list[str] = []
    actual_page_total = 0

    expected_metadata_paths = {
        ArtifactPaths.for_source(document.source_relpath).metadata
        for document in golden.documents
    }
    actual_metadata_paths = {
        path.relative_to(candidate_root).as_posix()
        for path in candidate_root.rglob("*.metadata.json")
    }
    for extra in sorted(actual_metadata_paths - expected_metadata_paths):
        if not _is_allowed_extra_metadata(
            candidate_root / Path(extra),
            raw_root,
            bijection_errors,
        ):
            bijection_errors.append(f"extra candidate metadata: {extra}")

    for document in golden.documents:
        paths = ArtifactPaths.for_source(document.source_relpath)
        source = raw_root / Path(document.source_relpath)
        if not source.exists():
            bijection_errors.append(f"{document.source_relpath}: source missing")

        metadata = _load_candidate_artifact(
            candidate_root / Path(paths.metadata),
            "metadata",
            document.source_relpath,
            bijection_errors,
        )
        pages = _load_candidate_artifact(
            candidate_root / Path(paths.pages),
            "pages",
            document.source_relpath,
            bijection_errors,
        )
        if isinstance(metadata, MetadataArtifact):
            metadata_errors.extend(_metadata_errors(document, metadata))
        if isinstance(pages, PagesArtifact):
            actual_page_total += pages.page_count
            page_errors.extend(_page_errors(document, pages))
            content_errors.extend(_content_errors(document, pages))

    expected_page_total = sum(document.page_count for document in golden.documents)
    total_errors = (
        []
        if actual_page_total == expected_page_total
        else [
            "candidate page total mismatch: "
            f"expected {expected_page_total}, got {actual_page_total}"
        ]
    )
    checks = [
        _check("golden_bijection", bijection_errors),
        _check("golden_metadata", metadata_errors),
        _check("golden_pages", page_errors),
        _check("golden_content", content_errors),
        _check("golden_page_total", total_errors),
    ]
    failed = sum(check.status == "failed" for check in checks)
    return ValidationReport(
        schema_version="2.0",
        run_id="golden",
        status="failed" if failed else "passed",
        documents_checked=len(golden.documents),
        errors=failed,
        checks=checks,
    )


def _load_candidate_artifact(
    path: Path,
    artifact_type: str,
    source_relpath: str,
    errors: list[str],
):
    if not path.exists():
        errors.append(f"{source_relpath}: {artifact_type} missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return load_artifact(payload, artifact_type)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"{source_relpath}: invalid {artifact_type}: {exc}")
        return None


def _is_allowed_extra_metadata(
    metadata_path: Path,
    raw_root: Path,
    errors: list[str],
) -> bool:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = load_artifact(payload, "metadata")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"{metadata_path.name}: invalid extra metadata: {exc}")
        return True
    if not isinstance(metadata, MetadataArtifact):
        return False
    source = raw_root / Path(metadata.source_relpath)
    if not source.exists():
        return False
    return source.suffix.lower() != ".pdf"


def _metadata_errors(
    document: GoldenDocument,
    metadata: MetadataArtifact,
) -> list[str]:
    errors: list[str] = []
    expected = document.expected
    _compare(errors, document, "document_id", document.document_id, metadata.document_id)
    _compare(
        errors,
        document,
        "source_relpath",
        document.source_relpath,
        metadata.source_relpath,
    )
    _compare(
        errors,
        document,
        "title",
        expected.title,
        metadata.document_control.title.value,
    )
    _compare(
        errors,
        document,
        "document_type",
        expected.document_type,
        metadata.classification.document_type,
    )
    _compare(errors, document, "topic", expected.topic, metadata.classification.topic)
    _compare(
        errors,
        document,
        "subtopic",
        expected.subtopic,
        metadata.classification.subtopic,
    )
    _compare(
        errors,
        document,
        "document_code",
        expected.document_code,
        metadata.document_control.code.value,
    )
    _compare(
        errors,
        document,
        "version",
        expected.version,
        metadata.document_control.version.value,
    )
    _compare(
        errors,
        document,
        "publication_date",
        expected.publication_date,
        metadata.document_control.publication_date.value,
    )
    _compare(
        errors,
        document,
        "effective_date",
        expected.effective_date,
        metadata.document_control.effective_date.value,
    )
    _compare(
        errors,
        document,
        "extraction_method",
        expected.extraction_method,
        metadata.extraction_method,
    )
    _compare(
        errors,
        document,
        "contains_tables",
        expected.contains_tables,
        metadata.tables.status,
    )
    _compare(
        errors,
        document,
        "contains_form",
        expected.contains_form,
        metadata.forms.status,
    )
    _compare(
        errors,
        document,
        "contains_handwriting",
        expected.contains_handwriting,
        metadata.handwriting.status,
    )
    _compare(
        errors,
        document,
        "version_status",
        expected.version_status,
        metadata.document_control.version.status,
    )
    _compare(
        errors,
        document,
        "processing_status",
        document.review_status,
        metadata.processing_status,
    )
    return errors


def _page_errors(
    document: GoldenDocument,
    pages: PagesArtifact,
) -> list[str]:
    errors: list[str] = []
    if pages.document_id != document.document_id:
        errors.append(
            f"{document.source_relpath}: pages document_id expected "
            f"{document.document_id!r}, got {pages.document_id!r}"
        )
    if pages.page_count != document.page_count:
        errors.append(
            f"{document.source_relpath}: page_count expected "
            f"{document.page_count}, got {pages.page_count}"
        )
    numbers = [page.page_number for page in pages.pages]
    expected_numbers = list(range(1, pages.page_count + 1))
    if numbers != expected_numbers:
        errors.append(
            f"{document.source_relpath}: page numbers expected "
            f"{expected_numbers}, got {numbers}"
        )
    return errors


def _content_errors(
    document: GoldenDocument,
    pages: PagesArtifact,
) -> list[str]:
    errors: list[str] = []
    pages_by_number = {
        page.page_number: page.text_normalized
        for page in pages.pages
    }
    for expectation in document.minimum_content:
        try:
            page_numbers = _parse_page_spec(expectation.pages)
        except ValueError as exc:
            errors.append(
                f"{document.source_relpath}: invalid minimum-content page "
                f"specification {expectation.pages!r}: {exc}"
            )
            continue
        available = [
            pages_by_number[number]
            for number in page_numbers
            if number in pages_by_number
        ]
        if len(available) != len(page_numbers):
            missing = sorted(set(page_numbers) - set(pages_by_number))
            errors.append(
                f"{document.source_relpath}: minimum-content pages "
                f"{expectation.pages!r} missing {missing}"
            )
            continue
        searchable = _normalized("\n".join(available))
        for required in expectation.must_preserve:
            if _normalized(required) not in searchable:
                errors.append(
                    f"{document.source_relpath}: pages "
                    f"{expectation.pages} missing required content "
                    f"{required!r}"
                )
    return errors


def _parse_page_spec(value: str) -> list[int]:
    numbers: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start < 1 or end < start:
                raise ValueError("range must be positive and ascending")
            numbers.update(range(start, end + 1))
        else:
            number = int(token)
            if number < 1:
                raise ValueError("page numbers must be positive")
            numbers.add(number)
    if not numbers:
        raise ValueError("at least one page is required")
    return sorted(numbers)


def _compare(
    errors: list[str],
    document: GoldenDocument,
    field: str,
    expected,
    actual,
) -> None:
    if expected is None:
        return
    if _normalized_for_field(field, expected) != _normalized_for_field(field, actual):
        errors.append(
            f"{document.source_relpath}: {field} expected "
            f"{expected!r}, got {actual!r}"
        )


def _normalized(value) -> str:
    text = _repair_mojibake(str(value))
    decomposed = unicodedata.normalize("NFD", text.casefold())
    text = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(text.split())


def _normalized_for_field(field: str, value) -> str:
    normalized = _normalized(value)
    if field == "document_code":
        return "".join(
            character
            for character in normalized
            if character.isalnum()
        )
    if field == "title":
        return normalized.rstrip(" .:;")
    return normalized


def _repair_mojibake(value: str) -> str:
    repaired = value
    for _attempt in range(2):
        if not any(marker in repaired for marker in ("\u00c3", "\u00c2", "\u00e2")):
            break
        try:
            candidate = repaired.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate.count("\u00c3") + candidate.count("\u00c2") >= (
            repaired.count("\u00c3") + repaired.count("\u00c2")
        ):
            break
        repaired = candidate
    return repaired


def _check(name: str, details: list[str]) -> ValidationCheck:
    return ValidationCheck(
        check=name,
        status="failed" if details else "passed",
        details=details,
    )
