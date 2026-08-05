from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Literal

from pydantic import ValidationError

from ingestion.inventory.scanner import compute_content_hash
from ingestion.schemas.artifacts import (
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
    ValidationCheck,
    ValidationReport,
)
from ingestion.schemas.inventory import InventoryRecord
from ingestion.validation.front_matter import parse_front_matter


Mode = Literal["normal", "closure"]
AUX_SUFFIXES = {
    ".pages.json": PagesArtifact,
    ".ocr.json": OcrArtifact,
    ".tables.json": TablesArtifact,
    ".forms.json": FormsArtifact,
}
FINAL_STATUSES = {"processed", "failed", "needs_review", "skipped"}


def validate_normalized_tree(
    normalized_root: Path,
    raw_root: Path | None = None,
    mode: Mode = "normal",
    golden_path: Path | None = None,
    run_id: str = "manual",
) -> ValidationReport:
    checks: list[ValidationCheck] = []
    manifests_root = normalized_root / "_manifests"
    metadata_files = sorted(normalized_root.rglob("*.metadata.json"))
    markdown_files = [
        path for path in sorted(normalized_root.rglob("*.md")) if "_manifests" not in path.parts
    ]
    aux_files = [
        path
        for path in sorted(normalized_root.rglob("*.json"))
        if any(path.name.endswith(suffix) for suffix in AUX_SUFFIXES)
    ]

    metadata_by_base: dict[Path, MetadataArtifact] = {}
    metadata_errors: list[str] = []
    legacy_warnings: list[str] = []
    document_ids: list[str] = []
    for path in metadata_files:
        try:
            payload = _read_json(path)
            if payload.get("schema_version") != "2.0":
                message = f"{path}: legacy schema_version={payload.get('schema_version')!r}"
                if mode == "closure":
                    metadata_errors.append(message)
                else:
                    legacy_warnings.append(message)
                continue
            metadata = MetadataArtifact(**payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            metadata_errors.append(f"{path}: {exc}")
            continue
        metadata_by_base[_artifact_base(path, ".metadata.json")] = metadata
        document_ids.append(metadata.document_id)

    checks.append(_check("metadata_schema", metadata_errors, warning=legacy_warnings))
    checks.append(_check("unique_document_ids", _duplicates(document_ids)))
    checks.append(
        _check(
            "markdown_has_metadata",
            [
                str(path)
                for path in markdown_files
                if _artifact_base(path, ".md") not in metadata_by_base
            ],
        )
    )

    checks.extend(_validate_auxiliary(aux_files, metadata_by_base))
    checks.extend(_validate_front_matter(markdown_files, metadata_by_base))
    checks.extend(_validate_inventory(manifests_root / "inventory.json", metadata_by_base, raw_root))
    checks.extend(_validate_status_manifests(manifests_root, metadata_by_base))

    if mode == "closure":
        checks.extend(_validate_closure_requirements(metadata_by_base, normalized_root))

    errors = sum(1 for check in checks if check.status == "failed")
    return ValidationReport(
        schema_version="2.0",
        run_id=run_id,
        status="failed" if errors else "passed",
        documents_checked=len(metadata_by_base),
        errors=errors,
        warnings=sum(1 for check in checks if check.status == "warning"),
        checks=checks,
    )


def _validate_auxiliary(
    aux_files: list[Path],
    metadata_by_base: dict[Path, MetadataArtifact],
) -> list[ValidationCheck]:
    orphan_errors: list[str] = []
    schema_errors: list[str] = []
    document_id_errors: list[str] = []
    page_errors: list[str] = []
    ordering_errors: list[str] = []
    for path in aux_files:
        suffix = _aux_suffix(path)
        base = _artifact_base(path, suffix)
        metadata = metadata_by_base.get(base)
        if metadata is None:
            orphan_errors.append(str(path))
            continue
        try:
            artifact = AUX_SUFFIXES[suffix](**_read_json(path))
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            schema_errors.append(f"{path}: {exc}")
            continue
        if getattr(artifact, "document_id", None) != metadata.document_id:
            document_id_errors.append(f"{path}: document_id mismatch")
        if isinstance(artifact, PagesArtifact):
            if artifact.page_count != metadata.page_count:
                page_errors.append(f"{path}: page_count {artifact.page_count} != metadata {metadata.page_count}")
            numbers = [page.page_number for page in artifact.pages]
            expected = list(range(1, len(numbers) + 1))
            if numbers != expected:
                ordering_errors.append(f"{path}: page numbers {numbers} != {expected}")
        if isinstance(artifact, TablesArtifact) and artifact.table_count != len(artifact.tables):
            page_errors.append(f"{path}: table_count mismatch")
    return [
        _check("orphan_files", orphan_errors),
        _check("auxiliary_schema", schema_errors),
        _check("auxiliary_document_ids", document_id_errors),
        _check("page_count_consistency", page_errors),
        _check("page_ordering_contiguity", ordering_errors),
    ]


def _validate_front_matter(
    markdown_files: list[Path],
    metadata_by_base: dict[Path, MetadataArtifact],
) -> list[ValidationCheck]:
    errors: list[str] = []
    for path in markdown_files:
        metadata = metadata_by_base.get(_artifact_base(path, ".md"))
        if metadata is None:
            continue
        front_matter = parse_front_matter(path)
        if front_matter.get("document_id") != metadata.document_id:
            errors.append(f"{path}: front matter document_id mismatch")
        if front_matter.get("source_relpath") and front_matter["source_relpath"] != metadata.source_relpath:
            errors.append(f"{path}: front matter source_relpath mismatch")
    return [_check("front_matter_parity", errors)]


def _validate_inventory(
    inventory_path: Path,
    metadata_by_base: dict[Path, MetadataArtifact],
    raw_root: Path | None,
) -> list[ValidationCheck]:
    if not inventory_path.exists():
        return [
            _check("inventory_schema", []),
            _check("inventory_metadata_bijection", []),
            _check("inventory_source_hashes", []),
            _check("inventory_final_statuses", []),
        ]
    schema_errors: list[str] = []
    hash_errors: list[str] = []
    final_status_errors: list[str] = []
    records: list[InventoryRecord] = []
    try:
        payload = _read_json(inventory_path)
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            payload = payload["records"]
        if not isinstance(payload, list):
            raise ValueError("inventory.json must be a list")
        records = [InventoryRecord(**item) for item in payload]
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        schema_errors.append(f"{inventory_path}: {exc}")
    for record in records:
        if record.processing_status not in FINAL_STATUSES:
            final_status_errors.append(f"{record.document_id}: {record.processing_status}")
        if raw_root is not None:
            source = raw_root / record.source_relpath
            if not source.exists():
                hash_errors.append(f"{record.document_id}: source missing")
            elif compute_content_hash(source) != record.content_hash:
                hash_errors.append(f"{record.document_id}: source hash mismatch")
    metadata_ids = {metadata.document_id for metadata in metadata_by_base.values()}
    inventory_ids = {record.document_id for record in records}
    processed_ids = {
        record.document_id
        for record in records
        if record.processing_status == "processed"
    }
    bijection_errors = sorted(
        (metadata_ids - inventory_ids)
        | (processed_ids - metadata_ids)
    )
    return [
        _check("inventory_schema", schema_errors),
        _check("inventory_metadata_bijection", bijection_errors),
        _check("inventory_source_hashes", hash_errors),
        _check("inventory_final_statuses", final_status_errors),
    ]


def _validate_status_manifests(
    manifests_root: Path,
    metadata_by_base: dict[Path, MetadataArtifact],
) -> list[ValidationCheck]:
    review_ids = _load_manifest_document_ids(manifests_root / "needs_review.json")
    error_ids = _load_manifest_document_ids(manifests_root / "errors.json")
    errors: list[str] = []
    processed_with_review_reasons: list[str] = []
    for metadata in metadata_by_base.values():
        if metadata.processing_status == "needs_review" and metadata.document_id not in review_ids:
            errors.append(f"{metadata.document_id}: missing from needs_review.json")
        if metadata.processing_status == "failed" and metadata.document_id not in error_ids:
            errors.append(f"{metadata.document_id}: missing from errors.json")
        if metadata.processing_status == "processed" and metadata.review_reasons:
            processed_with_review_reasons.append(metadata.document_id)
    return [
        _check("status_manifests", errors),
        _check("processed_with_review_reasons", processed_with_review_reasons),
    ]


def _validate_closure_requirements(
    metadata_by_base: dict[Path, MetadataArtifact],
    normalized_root: Path,
) -> list[ValidationCheck]:
    missing: list[str] = []
    for base, metadata in metadata_by_base.items():
        if metadata.document_name.lower().endswith(".pdf"):
            for suffix in (".pages.json", ".ocr.json", ".tables.json", ".forms.json"):
                artifact_path = base.with_name(base.name + suffix)
                if not artifact_path.exists():
                    missing.append(f"{metadata.source_relpath}: missing {suffix}")
    return [_check("closure_required_artifacts", missing)]


def _load_manifest_document_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return set()
    items = payload.get("items", payload.get("documents", []))
    return {
        item["document_id"]
        for item in items
        if isinstance(item, dict) and isinstance(item.get("document_id"), str)
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_base(path: Path, suffix: str) -> Path:
    return path.with_name(path.name[: -len(suffix)])


def _aux_suffix(path: Path) -> str:
    for suffix in AUX_SUFFIXES:
        if path.name.endswith(suffix):
            return suffix
    raise ValueError(f"Unsupported auxiliary artifact: {path}")


def _duplicates(values: Iterable[str]) -> list[str]:
    value_list = list(values)
    return sorted({value for value in value_list if value_list.count(value) > 1})


def _check(name: str, details: list[str], *, warning: list[str] | None = None) -> ValidationCheck:
    if details:
        return ValidationCheck(check=name, status="failed", details=details)
    if warning:
        return ValidationCheck(check=name, status="warning", details=warning)
    return ValidationCheck(check=name, status="passed", details=[])
