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
from ingestion.manifests.writer import dump_json  # noqa: E402
from ingestion.validation.normalized import validate_normalized_tree  # noqa: E402
from core.logging.logger import configure_structured_logging  # noqa: E402


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    logger = logging.getLogger(__name__)
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Validate data/docs_normalized artifacts.")
    parser.add_argument("--docs-normalized", type=Path, default=ROOT / "data" / "docs_normalized")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help="Raw corpus root used for source hashes and golden validation.",
    )
    parser.add_argument(
        "--mode",
        choices=("normal", "closure"),
        default="normal",
        help="Use closure to reject legacy artifacts and require every PDF sidecar.",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=None,
        help=(
            "Deprecated and ignored by validate stage. "
            "Run corpus golden tests separately when auditing fixed fixtures."
        ),
    )
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = validate_normalized_tree(
        args.docs_normalized,
        raw_root=args.raw_root,
        mode=args.mode,
        run_id=args.run_id,
    )
    output = args.output or args.docs_normalized / "_manifests" / f"validation_{args.run_id}.json"
    dump_json(output, report)
    logger.info(
        "validation_report_written",
        extra={
            "stage": "validation",
            "event": "validation_report_written",
            "status": report.status,
            "error_count": len(report.errors),
            "output": str(output),
            "run_id": args.run_id,
        },
    )
    print(
        json.dumps(
            {
                "status": report.status,
                "error_count": len(report.errors),
                "run_id": args.run_id,
                "output": str(output),
                "docs_normalized": str(args.docs_normalized),
                "mode": args.mode,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
