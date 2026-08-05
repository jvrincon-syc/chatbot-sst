from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from chunking.api.app import create_app
from chunking.application.chunking_orchestrator import ChunkingOrchestrator
from chunking.application.local_chunking_engine import LocalChunkingEngine
from chunking.domain.models import ChunkingProfile
from chunking.infrastructure.filesystem_chunk_repository import (
    FilesystemChunkBundleRepository,
)
from chunking.infrastructure.filesystem_run_repository import FilesystemRunRepository
from chunking.infrastructure.schema2_source import Schema2NormalizedDocumentSource
from core.logging.logger import configure_structured_logging  # noqa: E402
from ingestion.paths import ArtifactPaths


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationContext:
    source: Schema2NormalizedDocumentSource
    orchestrator: ChunkingOrchestrator
    repository: FilesystemChunkBundleRepository
    profile: ChunkingProfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local chunking outputs.")
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--chunks-root", default="manual-test-temp/chunking-validation")
    parser.add_argument("--profile", default="local-structural-v1")
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--expected-json")
    parser.add_argument("--openapi-output")
    parser.add_argument(
        "--skip-rerun-compare",
        action="store_true",
        help="Skip the second identical run comparison.",
    )
    return parser.parse_args()


def validate_chunk_outputs(
    *,
    docs_normalized: Path,
    chunks_root: Path,
    profile_id: str = "local-structural-v1",
    document_ids: list[str] | None = None,
    expected_json: Path | None = None,
    openapi_output: Path | None = None,
    compare_rerun: bool = True,
) -> dict[str, Any]:
    docs_root = docs_normalized.resolve()
    chunks_root = chunks_root.resolve()
    inventory_records = _eligible_inventory_records(docs_root)
    selected_records = _select_records(inventory_records, document_ids=document_ids or [])
    before_hash = _snapshot_tree(docs_root)
    context = _build_context(docs_root=docs_root, chunks_root=chunks_root, profile_id=profile_id)
    document_summaries: list[dict[str, Any]] = []
    details_by_document_id: dict[str, dict[str, Any]] = {}

    for record in selected_records:
        source_relpath = str(record["source_relpath"])
        normalized_relpath = ArtifactPaths.for_source(source_relpath).markdown
        document = context.source.load(normalized_relpath)
        first = context.orchestrator.process_document(
            document=document,
            profile=context.profile,
        )
        second = (
            context.orchestrator.process_document(
                document=document,
                profile=context.profile,
            )
            if compare_rerun
            else None
        )
        if second is not None:
            _assert_identical_rerun(first=first, second=second, document_id=document.document_id)

        parents = context.repository.read_parents(normalized_relpath=document.normalized_relpath)
        children = context.repository.read_children(normalized_relpath=document.normalized_relpath)
        summary = {
            "document_id": document.document_id,
            "source_relpath": document.source_relpath,
            "normalized_relpath": document.normalized_relpath,
            "parent_count": len(parents),
            "child_count": len(children),
            "warnings": list(document.warnings),
            "tables_present": document.sidecars.tables_present,
            "forms_present": document.sidecars.forms_present,
            "ocr_present": document.sidecars.ocr_present,
            "any_parent_cross_page": any(_spans_multiple_pages(parent) for parent in parents),
            "zero_overlap_reasons": sorted(
                {
                    reason
                    for child in children
                    for reason in child.get("zero_overlap_reasons", [])
                    if isinstance(reason, str)
                }
            ),
            "reused_on_second_run": second.reused if second is not None else None,
            "run_id_stable": second.run_id == first.run_id if second is not None else None,
        }
        document_summaries.append(summary)
        details_by_document_id[document.document_id] = {
            "parents": parents,
            "children": children,
        }
        logger.info(
            "Validated chunk bundle",
            extra={
                "document_id": document.document_id,
                "run_id": first.run_id,
                "parent_count": len(parents),
                "child_count": len(children),
                "reused_on_second_run": summary["reused_on_second_run"],
            },
        )

    after_hash = _snapshot_tree(docs_root)
    if before_hash != after_hash:
        raise ValueError("docs_normalized changed during chunk validation")

    openapi_path = None
    if openapi_output is not None:
        openapi_path = _export_openapi(
            docs_normalized=docs_root,
            chunks_root=chunks_root,
            output_path=openapi_output,
        )

    result = {
        "docs_normalized": docs_root.as_posix(),
        "chunks_root": chunks_root.as_posix(),
        "documents_checked": len(document_summaries),
        "compare_rerun": compare_rerun,
        "docs_unchanged": True,
        "openapi_output": openapi_path.as_posix() if openapi_path is not None else None,
        "documents": document_summaries,
    }
    if expected_json is not None:
        expected_payload = json.loads(expected_json.read_text(encoding="utf-8"))
        _validate_expected_contract(
            result=result,
            expected_payload=expected_payload,
            details_by_document_id=details_by_document_id,
        )
        result["expected_contract"] = expected_json.as_posix()
    return result


def _build_context(
    *,
    docs_root: Path,
    chunks_root: Path,
    profile_id: str,
) -> ValidationContext:
    repository = FilesystemChunkBundleRepository(output_root=chunks_root)
    return ValidationContext(
        source=Schema2NormalizedDocumentSource(docs_normalized=docs_root),
        orchestrator=ChunkingOrchestrator(
            engine=LocalChunkingEngine(),
            bundle_repository=repository,
            run_repository=FilesystemRunRepository(output_root=chunks_root),
        ),
        repository=repository,
        profile=_profile(profile_id),
    )


def _profile(profile_id: str) -> ChunkingProfile:
    if profile_id != "local-structural-v1":
        raise ValueError(f"unsupported local chunking profile: {profile_id}")
    return ChunkingProfile.local_structural_v1()


def _eligible_inventory_records(docs_root: Path) -> list[dict[str, Any]]:
    inventory_path = docs_root / "_manifests" / "inventory.json"
    if not inventory_path.exists():
        return [
            {
                "document_id": path.stem,
                "source_relpath": path.relative_to(docs_root).as_posix(),
                "processing_status": "processed",
            }
            for path in sorted(docs_root.rglob("*.md"))
            if "_manifests" not in path.parts
        ]
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    return [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("document_id")
        and record.get("source_relpath")
        and record.get("processing_status") == "processed"
    ]


def _select_records(
    records: list[dict[str, Any]],
    *,
    document_ids: list[str],
) -> list[dict[str, Any]]:
    if not document_ids:
        return records
    index = {str(record["document_id"]): record for record in records}
    missing = [document_id for document_id in document_ids if document_id not in index]
    if missing:
        raise ValueError(f"unknown processed document ids: {', '.join(sorted(missing))}")
    return [index[document_id] for document_id in document_ids]


def _assert_identical_rerun(*, first, second, document_id: str) -> None:
    if first.run_id != second.run_id:
        raise ValueError(f"rerun changed run_id for {document_id}")
    if first.bundle_fingerprint != second.bundle_fingerprint:
        raise ValueError(f"rerun changed bundle fingerprint for {document_id}")
    if second.reused is not True:
        raise ValueError(f"rerun did not reuse persisted artifacts for {document_id}")


def _snapshot_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    }


def _spans_multiple_pages(parent_payload: dict[str, Any]) -> bool:
    source_span = parent_payload.get("source_span", {})
    page_start = source_span.get("page_start")
    page_end = source_span.get("page_end")
    return page_start is not None and page_end is not None and page_start != page_end


def _export_openapi(
    *,
    docs_normalized: Path,
    chunks_root: Path,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    app = create_app(docs_normalized=docs_normalized, chunks_root=chunks_root)
    try:
        payload = app.openapi()
    finally:
        app.state.chunking_run_service.close()
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _validate_expected_contract(
    *,
    result: dict[str, Any],
    expected_payload: dict[str, Any],
    details_by_document_id: dict[str, dict[str, Any]],
) -> None:
    cases = expected_payload.get("cases", [])
    summaries = {
        document["document_id"]: document
        for document in result["documents"]
        if isinstance(document, dict) and document.get("document_id")
    }
    if len(cases) != result["documents_checked"]:
        raise ValueError("golden cases count does not match validated documents count")
    for case in cases:
        document_id = str(case["document_id"])
        summary = summaries.get(document_id)
        if summary is None:
            raise ValueError(f"missing validated summary for golden document {document_id}")
        expected = case.get("expected", {})
        _assert_expected_field(summary, "parent_count", expected)
        _assert_minimum(summary, "child_count", expected, expected_key="child_count_min")
        _assert_expected_field(summary, "tables_present", expected)
        _assert_expected_field(summary, "forms_present", expected)
        _assert_expected_field(summary, "ocr_present", expected)
        _assert_expected_field(summary, "any_parent_cross_page", expected)
        required_reasons = expected.get("required_zero_overlap_reasons", [])
        summary_reasons = set(summary.get("zero_overlap_reasons", []))
        if any(reason not in summary_reasons for reason in required_reasons):
            raise ValueError(f"missing zero-overlap reason in {document_id}")
        literal_substrings = expected.get("literal_substrings", [])
        materialized_text = _materialized_text(details_by_document_id[document_id])
        for literal in literal_substrings:
            if literal not in materialized_text:
                raise ValueError(f"literal '{literal}' was not preserved in {document_id}")


def _assert_expected_field(
    summary: dict[str, Any],
    field_name: str,
    expected: dict[str, Any],
) -> None:
    if field_name not in expected:
        return
    if summary.get(field_name) != expected[field_name]:
        raise ValueError(f"{field_name} mismatch for {summary['document_id']}")


def _assert_minimum(
    summary: dict[str, Any],
    field_name: str,
    expected: dict[str, Any],
    *,
    expected_key: str,
) -> None:
    if expected_key not in expected:
        return
    if int(summary.get(field_name, 0)) < int(expected[expected_key]):
        raise ValueError(f"{field_name} is below expected minimum for {summary['document_id']}")


def _materialized_text(details: dict[str, Any]) -> str:
    parents = details.get("parents", [])
    children = details.get("children", [])
    parts = [str(parent.get("text", "")) for parent in parents]
    parts.extend(str(child.get("text", "")) for child in children)
    parts.extend(str(child.get("context_prefix", "")) for child in children)
    return "\n".join(parts)


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    args = parse_args()
    logger.info(
        "chunking_validation_started",
        extra={
            "stage": "chunking",
            "event": "chunking_validation_started",
            "status": "started",
            "docs_normalized": args.docs_normalized,
            "chunks_root": args.chunks_root,
            "profile": args.profile,
        },
    )
    result = validate_chunk_outputs(
        docs_normalized=Path(args.docs_normalized),
        chunks_root=Path(args.chunks_root),
        profile_id=args.profile,
        document_ids=list(args.document_id),
        expected_json=Path(args.expected_json) if args.expected_json else None,
        openapi_output=Path(args.openapi_output) if args.openapi_output else None,
        compare_rerun=not args.skip_rerun_compare,
    )
    logger.info(
        "chunking_validation_completed",
        extra={
            "stage": "chunking",
            "event": "chunking_validation_completed",
            "status": "completed",
            "docs_normalized": args.docs_normalized,
            "chunks_root": args.chunks_root,
            "profile": args.profile,
            "document_count": result["documents_checked"],
        },
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
