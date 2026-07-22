from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Sequence
from pydantic import Field

from ingestion.paths import ArtifactPaths
from ingestion.schemas.common import StrictModel


class IndexValidationReport(StrictModel):
    status: str
    profile_id: str | None = None
    ingestion_origin: str | None = None
    vector_table: str | None = None
    indexed_documents: int = Field(ge=0)
    indexed_child_nodes: int = Field(ge=0)
    orphan_vectors: int = Field(ge=0)
    mixed_provider_errors: int = Field(ge=0)
    dimension_errors: int = Field(ge=0)
    unapproved_document_errors: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Llama-first index state.")
    parser.add_argument("--docs-normalized", default="data/docs_normalized")
    parser.add_argument("--profile", default="llama-first-local-v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_index_state(
        normalized_root=Path(args.docs_normalized),
        profile=args.profile,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def validate_index_state(
    *,
    normalized_root: Path | None = None,
    profile: str = "llama-first-local-v1",
    documents: Sequence[dict[str, object]] | None = None,
    profiles: Sequence[dict[str, object]] | None = None,
    vectors: Sequence[dict[str, object]] | None = None,
    nodes: Sequence[dict[str, object]] | None = None,
) -> dict | IndexValidationReport:
    if documents is not None or profiles is not None or vectors is not None:
        return _validate_rows(
            documents=documents or [],
            profiles=profiles or [],
            vectors=vectors or [],
            nodes=nodes or [],
        )

    if normalized_root is None:
        raise ValueError("normalized_root is required for artifact validation")
    manifest_path = normalized_root / "_manifests" / "inventory.json"
    if not manifest_path.exists():
        return {
            "status": "failed",
            "errors": ["inventory_manifest_not_found"],
            "profile": profile,
        }

    inventory = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = inventory.get("records", inventory if isinstance(inventory, list) else [])
    errors: list[str] = []
    approved_documents = 0
    for record in records:
        if record.get("processing_status") != "processed":
            continue
        approved_documents += 1
        paths = ArtifactPaths.for_source(record["source_relpath"])
        for relpath in (
            paths.markdown,
            paths.metadata,
            paths.pages,
            paths.tables,
            paths.forms,
        ):
            if not (normalized_root / relpath).exists():
                errors.append(f"missing_artifact:{relpath}")

    return {
        "status": "failed" if errors else "passed",
        "profile": profile,
        "checks": ["inventory_manifest_present", "approved_artifacts_present"],
        "approved_documents": approved_documents,
        "errors": errors,
    }


def _validate_rows(
    *,
    documents: Sequence[dict[str, object]],
    profiles: Sequence[dict[str, object]],
    vectors: Sequence[dict[str, object]],
    nodes: Sequence[dict[str, object]],
) -> IndexValidationReport:
    document_by_id = {str(document["document_id"]): document for document in documents}
    profile_by_id = {str(profile["profile_id"]): profile for profile in profiles}
    node_ids = {str(node["node_id"]) for node in nodes}
    child_node_ids = {
        str(node["node_id"])
        for node in nodes
        if str(node.get("node_role", "")) == "child"
    }
    errors: list[str] = []
    orphan_vectors = 0
    mixed_provider_errors = 0
    dimension_errors = 0
    unapproved_document_errors = 0

    for vector in vectors:
        document_id = str(vector.get("document_id", ""))
        profile_id = str(vector.get("profile_id", ""))
        node_id = str(vector.get("node_id", ""))
        document = document_by_id.get(document_id)
        profile = profile_by_id.get(profile_id)

        if node_id not in node_ids or node_id not in child_node_ids:
            orphan_vectors += 1
            errors.append(f"orphan_vector:{node_id}")
        if document is None or document.get("approved") is not True:
            unapproved_document_errors += 1
            errors.append(f"unapproved_document_vector:{document_id}")
        if document is not None and profile is not None:
            if document.get("ingestion_origin") != profile.get("ingestion_origin"):
                mixed_provider_errors += 1
                errors.append(f"mixed_profile_lane:{document_id}:{profile_id}")
        if profile is not None:
            if vector.get("embedding_dimension") != profile.get("embedding_dimension"):
                dimension_errors += 1
                errors.append(f"dimension_mismatch:{node_id}:{profile_id}")

    status = "failed" if errors else "passed"
    first_profile = profiles[0] if profiles else {}
    return IndexValidationReport(
        status=status,
        profile_id=(
            str(first_profile["profile_id"])
            if "profile_id" in first_profile
            else None
        ),
        ingestion_origin=(
            str(first_profile["ingestion_origin"])
            if "ingestion_origin" in first_profile
            else None
        ),
        vector_table=(
            str(first_profile["vector_table"])
            if "vector_table" in first_profile
            else None
        ),
        indexed_documents=len({str(vector.get("document_id", "")) for vector in vectors}),
        indexed_child_nodes=len(vectors),
        orphan_vectors=orphan_vectors,
        mixed_provider_errors=mixed_provider_errors,
        dimension_errors=dimension_errors,
        unapproved_document_errors=unapproved_document_errors,
        errors=errors,
    )


if __name__ == "__main__":
    raise SystemExit(main())
