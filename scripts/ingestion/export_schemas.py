#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.manifests.writer import write_text_atomic  # noqa: E402
from ingestion.schemas.artifacts import (  # noqa: E402
    FormsArtifact,
    MetadataArtifact,
    OcrArtifact,
    PagesArtifact,
    TablesArtifact,
)
from ingestion.schemas.manifests import (  # noqa: E402
    BundleManifest,
    ErrorManifest,
    InventoryManifest,
    ReviewManifest,
    RunManifest,
)


SCHEMAS = {
    "metadata.schema.json": MetadataArtifact,
    "pages.schema.json": PagesArtifact,
    "ocr.schema.json": OcrArtifact,
    "tables.schema.json": TablesArtifact,
    "forms.schema.json": FormsArtifact,
    "inventory.schema.json": InventoryManifest,
    "run.schema.json": RunManifest,
    "review.schema.json": ReviewManifest,
    "errors.schema.json": ErrorManifest,
    "bundle.schema.json": BundleManifest,
}


def main() -> int:
    output_dir = ROOT / "app" / "back" / "src" / "ingestion" / "schemas" / "json"
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        write_text_atomic(
            output_dir / filename,
            json.dumps(
                schema,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    print(f"Exported {len(SCHEMAS)} schemas -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
