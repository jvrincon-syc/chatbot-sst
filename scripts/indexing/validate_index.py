from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.paths import ArtifactPaths


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


def validate_index_state(*, normalized_root: Path, profile: str) -> dict:
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


if __name__ == "__main__":
    raise SystemExit(main())
