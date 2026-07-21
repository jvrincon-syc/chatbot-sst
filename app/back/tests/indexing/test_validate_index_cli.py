from __future__ import annotations

import json

from scripts.indexing.validate_index import validate_index_state


def test_validate_index_state_fails_when_approved_artifact_is_missing(tmp_path) -> None:
    root = tmp_path / "docs_normalized"
    manifests = root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_relpath": "manual/doc.pdf",
                        "processing_status": "processed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_index_state(normalized_root=root, profile="test")

    assert result["status"] == "failed"
    assert "missing_artifact:manual/doc.md" in result["errors"]


def test_validate_index_state_passes_when_approved_artifacts_exist(tmp_path) -> None:
    root = tmp_path / "docs_normalized"
    manifests = root / "_manifests"
    manifests.mkdir(parents=True)
    (manifests / "inventory.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_relpath": "manual/doc.pdf",
                        "processing_status": "processed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for suffix in (".md", ".metadata.json", ".pages.json", ".tables.json", ".forms.json"):
        target = root / f"manual/doc{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

    result = validate_index_state(normalized_root=root, profile="test")

    assert result["status"] == "passed"
    assert result["approved_documents"] == 1
