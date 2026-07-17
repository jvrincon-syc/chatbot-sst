from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from pydantic import ValidationError

from ingestion.inventory.scanner import compute_content_hash
from ingestion.schemas.artifacts import (
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
    ValidationCheck,
    ValidationReport,
)
from ingestion.schemas.inventory import InventoryRecord


AUX_SUFFIXES = [".pages.json", ".ocr.json", ".tables.json"]
FINAL_STATUSES = {"processed", "failed", "needs_review", "skipped"}


def _metadata_base(path: Path) -> Path:
    return path.with_name(path.name[: -len(".metadata.json")])


def _aux_base(path: Path) -> Path:
    for suffix in AUX_SUFFIXES:
        if path.name.endswith(suffix):
            return path.with_name(path.name[: -len(suffix)])
    return path


def _check(name: str, details: Iterable[str]) -> ValidationCheck:
    detail_list = list(details)
    return ValidationCheck(
        check=name,
        status="failed" if detail_list else "passed",
        details=detail_list,
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest_document_ids(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return set()
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        return set()
    ids: Set[str] = set()
    for document in documents:
        if isinstance(document, dict) and isinstance(document.get("document_id"), str):
            ids.add(document["document_id"])
    return ids


def _parse_auxiliary(path: Path) -> object:
    payload = _read_json(path)
    if path.name.endswith(".pages.json"):
        return PagesArtifact(**payload)
    if path.name.endswith(".ocr.json"):
        return OcrArtifact(**payload)
    if path.name.endswith(".tables.json"):
        return TablesArtifact(**payload)
    raise ValueError(f"Unsupported auxiliary artifact: {path}")


def _schema_version_error(path: Path, artifact: object) -> Optional[str]:
    schema_version = getattr(artifact, "schema_version", None)
    if schema_version != "1.0":
        return f"{path}: unsupported schema_version={schema_version!r}"
    return None


def validate_normalized_tree(normalized_root: Path, run_id: str = "manual") -> ValidationReport:
    checks: List[ValidationCheck] = []
    manifests_root = normalized_root / "_manifests"

    markdown_files = [
        path
        for path in normalized_root.rglob("*.md")
        if "_manifests" not in path.parts
    ]
    metadata_files = list(normalized_root.rglob("*.metadata.json"))
    aux_files = [
        path
        for path in normalized_root.rglob("*.json")
        if any(path.name.endswith(suffix) for suffix in AUX_SUFFIXES)
    ]

    missing_metadata = [
        str(path)
        for path in markdown_files
        if not path.with_name(path.stem + ".metadata.json").exists()
    ]
    checks.append(_check("markdown_has_metadata", missing_metadata))

    metadata_by_base: Dict[Path, MetadataArtifact] = {}
    invalid_metadata: List[str] = []
    document_ids: List[str] = []
    for path in metadata_files:
        try:
            metadata = MetadataArtifact(**_read_json(path))
            version_error = _schema_version_error(path, metadata)
            if version_error:
                invalid_metadata.append(version_error)
            metadata_by_base[_metadata_base(path)] = metadata
            document_ids.append(metadata.document_id)
        except (json.JSONDecodeError, ValidationError) as exc:
            invalid_metadata.append(f"{path}: {exc}")
    checks.append(_check("metadata_schema", invalid_metadata))

    duplicate_ids = sorted({document_id for document_id in document_ids if document_ids.count(document_id) > 1})
    checks.append(_check("unique_document_ids", duplicate_ids))

    missing_markdown = [
        metadata.normalized_path
        for metadata in metadata_by_base.values()
        if metadata.processing_status == "processed" and not Path(metadata.normalized_path).exists()
    ]
    checks.append(_check("processed_metadata_references_markdown", missing_markdown))

    metadata_bases: Set[Path] = set(metadata_by_base)
    orphan_files = [str(path) for path in aux_files if _aux_base(path) not in metadata_bases]
    checks.append(_check("orphan_files", orphan_files))

    aux_document_id_errors: List[str] = []
    aux_schema_errors: List[str] = []
    page_count_errors: List[str] = []
    for path in aux_files:
        base = _aux_base(path)
        metadata = metadata_by_base.get(base)
        if metadata is None:
            continue
        try:
            artifact = _parse_auxiliary(path)
            version_error = _schema_version_error(path, artifact)
            if version_error:
                aux_schema_errors.append(version_error)
                continue
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            aux_schema_errors.append(f"{path}: {exc}")
            continue

        artifact_document_id = getattr(artifact, "document_id", None)
        if artifact_document_id != metadata.document_id:
            aux_document_id_errors.append(f"{path}: {artifact_document_id} != {metadata.document_id}")

        if isinstance(artifact, PagesArtifact):
            if artifact.page_count != len(artifact.pages):
                page_count_errors.append(f"{path}: page_count={artifact.page_count} pages={len(artifact.pages)}")
            if artifact.page_count != metadata.page_count:
                page_count_errors.append(
                    f"{path}: page_count={artifact.page_count} metadata={metadata.page_count}"
                )
        elif isinstance(artifact, OcrArtifact):
            if metadata.extraction_method == "ocr" and len(artifact.pages) != metadata.page_count:
                page_count_errors.append(f"{path}: ocr_pages={len(artifact.pages)} metadata={metadata.page_count}")
        elif isinstance(artifact, TablesArtifact):
            if artifact.table_count != len(artifact.tables):
                page_count_errors.append(f"{path}: table_count={artifact.table_count} tables={len(artifact.tables)}")

    checks.append(_check("auxiliary_schema", aux_schema_errors))
    checks.append(_check("auxiliary_document_ids", aux_document_id_errors))
    checks.append(_check("page_count_consistency", page_count_errors))

    inventory_errors: List[str] = []
    inventory_hash_errors: List[str] = []
    inventory_final_status_errors: List[str] = []
    inventory_ids: List[str] = []
    inventory_path = manifests_root / "inventory.json"
    if inventory_path.exists():
        try:
            inventory_payload = _read_json(inventory_path)
            if not isinstance(inventory_payload, list):
                raise ValueError("inventory.json must be a list")
            inventory_records = [InventoryRecord(**item) for item in inventory_payload]
            inventory_ids = [record.document_id for record in inventory_records]
            for record in inventory_records:
                if record.processing_status not in FINAL_STATUSES:
                    inventory_final_status_errors.append(f"{record.document_id}: {record.processing_status}")
                source_path = Path(record.source_path)
                if source_path.exists():
                    actual_hash = compute_content_hash(source_path)
                    if actual_hash != record.content_hash:
                        inventory_hash_errors.append(f"{record.document_id}: {actual_hash} != {record.content_hash}")
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            inventory_errors.append(f"{inventory_path}: {exc}")

    inventory_duplicate_ids = sorted(
        {document_id for document_id in inventory_ids if inventory_ids.count(document_id) > 1}
    )
    checks.append(_check("inventory_schema", inventory_errors))
    checks.append(_check("inventory_unique_document_ids", inventory_duplicate_ids))
    checks.append(_check("inventory_source_hashes", inventory_hash_errors))
    checks.append(_check("inventory_final_statuses", inventory_final_status_errors))

    review_ids = _load_manifest_document_ids(manifests_root / "needs_review.json")
    error_ids = _load_manifest_document_ids(manifests_root / "errors.json")
    status_manifest_errors: List[str] = []
    processed_failed_conflicts: List[str] = []
    for metadata in metadata_by_base.values():
        if metadata.processing_status == "needs_review" and metadata.document_id not in review_ids:
            status_manifest_errors.append(f"{metadata.document_id}: needs_review missing from needs_review.json")
        if metadata.processing_status == "failed" and metadata.document_id not in error_ids:
            status_manifest_errors.append(f"{metadata.document_id}: failed missing from errors.json")
        if metadata.processing_status == "processed" and metadata.document_id in error_ids:
            processed_failed_conflicts.append(f"{metadata.document_id}: processed metadata and errors.json")

    checks.append(_check("status_manifests", status_manifest_errors))
    checks.append(_check("processed_failed_conflicts", processed_failed_conflicts))

    errors = sum(1 for check in checks if check.status == "failed")
    return ValidationReport(
        run_id=run_id,
        status="failed" if errors else "passed",
        documents_checked=len(metadata_files),
        errors=errors,
        checks=checks,
    )
