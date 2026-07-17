#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.env import load_secrets_env  # noqa: E402
from ingestion.manifests.writer import dump_json  # noqa: E402
from ingestion.validation.normalized import validate_normalized_tree  # noqa: E402


def main() -> int:
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Validate data/docs_normalized artifacts.")
    parser.add_argument("--docs-normalized", type=Path, default=ROOT / "data" / "docs_normalized")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = validate_normalized_tree(args.docs_normalized, run_id=args.run_id)
    output = args.output or args.docs_normalized / "_manifests" / f"validation_{args.run_id}.json"
    dump_json(output, report)
    print(f"{report.status}: {report.errors} error(s) -> {output}")
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
