#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.env import load_secrets_env  # noqa: E402
from ingestion.pipeline import run_pipeline  # noqa: E402


def main() -> int:
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Run ingestion normalization pipeline.")
    parser.add_argument("--docs-raw", type=Path, default=ROOT / "data" / "docs_raw")
    parser.add_argument("--docs-normalized", type=Path, default=ROOT / "data" / "docs_normalized")
    parser.add_argument("--corpus-version", default="1")
    parser.add_argument("--pipeline-version", default="1.0.0")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    summary = run_pipeline(
        docs_raw=args.docs_raw,
        docs_normalized=args.docs_normalized,
        corpus_version=args.corpus_version,
        pipeline_version=args.pipeline_version,
        run_id=args.run_id,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
