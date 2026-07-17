#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.schemas.artifacts import MetadataArtifact, OcrArtifact, PagesArtifact, TablesArtifact  # noqa: E402


SCHEMAS = {
    "metadata.schema.json": MetadataArtifact,
    "pages.schema.json": PagesArtifact,
    "ocr.schema.json": OcrArtifact,
    "tables.schema.json": TablesArtifact,
}


def main() -> int:
    output_dir = ROOT / "app" / "back" / "src" / "ingestion" / "schemas" / "json"
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (output_dir / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Exported {len(SCHEMAS)} schemas -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
