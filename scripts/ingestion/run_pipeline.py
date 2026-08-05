#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.env import load_secrets_env  # noqa: E402
from ingestion.pipeline import run_pipeline  # noqa: E402
from core.logging.logger import configure_structured_logging  # noqa: E402


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    logger = logging.getLogger(__name__)
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Run ingestion normalization pipeline.")
    parser.add_argument("--docs-raw", type=Path, default=ROOT / "data" / "docs_raw")
    parser.add_argument("--docs-normalized", type=Path, default=ROOT / "data" / "docs_normalized")
    parser.add_argument("--staging-root", type=Path, default=None)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--golden-status", choices=("passed", "failed"), default=None)
    parser.add_argument("--only-source", action="append", dest="only_sources")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--corpus-version", default="1")
    parser.add_argument("--pipeline-version", default="1.0.0")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--ocr-review-threshold",
        type=float,
        default=0.80,
        help="Minimum OCR confidence ratio required before marking a PDF for review.",
    )
    args = parser.parse_args()
    run_id = args.run_id or "run_" + datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")

    summary = run_pipeline(
        docs_raw=args.docs_raw,
        docs_normalized=args.docs_normalized,
        staging_root=args.staging_root,
        promote=args.promote,
        only_sources=args.only_sources,
        force=args.force,
        corpus_version=args.corpus_version,
        pipeline_version=args.pipeline_version,
        run_id=run_id,
        ocr_review_threshold=args.ocr_review_threshold,
        golden_status=args.golden_status,
        request_id=f"cli_{run_id}",
    )
    logger.info(
        "ingestion_pipeline_finished",
        extra={
            "run_id": run_id,
            "stage": "pipeline",
            "event": "pipeline_finished",
            "status": "completed",
            "summary": summary,
        },
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "run_id": run_id,
                "summary": summary,
                "docs_raw": str(args.docs_raw),
                "docs_normalized": str(args.docs_normalized),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
