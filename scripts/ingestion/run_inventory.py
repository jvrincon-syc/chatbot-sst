#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.env import load_secrets_env  # noqa: E402
from ingestion.inventory.scanner import scan_docs_raw  # noqa: E402
from ingestion.manifests.writer import write_inventory  # noqa: E402
from core.logging.logger import configure_structured_logging  # noqa: E402


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    logger = logging.getLogger(__name__)
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Scan data/docs_raw and write inventory.json.")
    parser.add_argument("--docs-raw", type=Path, default=ROOT / "data" / "docs_raw")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "docs_normalized" / "_manifests" / "inventory.json")
    parser.add_argument("--corpus-version", default="1")
    parser.add_argument("--pipeline-version", default="1.0.0")
    args = parser.parse_args()

    records = scan_docs_raw(
        args.docs_raw,
        corpus_version=args.corpus_version,
        pipeline_version=args.pipeline_version,
    )
    write_inventory(args.output, records)
    logger.info(
        "inventory_written",
        extra={
            "stage": "inventory",
            "event": "inventory_written",
            "status": "completed",
            "document_count": len(records),
            "output": str(args.output),
        },
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "document_count": len(records),
                "output": str(args.output),
                "docs_raw": str(args.docs_raw),
                "corpus_version": args.corpus_version,
                "pipeline_version": args.pipeline_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
