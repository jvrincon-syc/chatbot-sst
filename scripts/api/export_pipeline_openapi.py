#!/usr/bin/env python3
"""Export the bundle-first pipeline OpenAPI schema to ``docs/api``.

The schema is generated from the real FastAPI app wired on in-memory adapters
with every rollout flag on, so every route (including the flag-gated ones) is
present in the document. Output is canonical: sorted keys, two-space indent and
a trailing newline, so re-exports produce minimal diffs.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from api.app import create_app  # noqa: E402
from api.dependencies import build_pipeline_services  # noqa: E402
from core.consumer_scope import ConsumerScope  # noqa: E402
from core.feature_flags import FeatureFlags  # noqa: E402


OUTPUT = ROOT / "docs" / "api" / "pipeline-openapi.json"


def build_schema() -> dict:
    """Build the OpenAPI schema from the real application."""

    services = build_pipeline_services(
        chunks_root=ROOT / ".tmp" / "openapi-export" / "chunks",
        embeddings_root=ROOT / ".tmp" / "openapi-export" / "embeddings",
        feature_flags=FeatureFlags(
            embedding_v2=True,
            indexing_bundle_first=True,
            retrieval_v1=True,
            # Fase 7: exporta también la superficie administrativa de plataforma.
            rag_platform_v1=True,
        ),
        consumer_scope=ConsumerScope(),
        allow_mock_engine=True,
    )
    try:
        app = create_app(services=services)
        return app.openapi()
    finally:
        services.close()


def main() -> int:
    schema = build_schema()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(schema, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
