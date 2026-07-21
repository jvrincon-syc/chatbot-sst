from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Llama-first benchmark.")
    parser.add_argument("--evaluation-root", default="data/evaluation/llama_first")
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    args = parse_args()
    root = Path(args.evaluation_root)
    documents = _read_jsonl(root / "documents.jsonl")
    questions = _read_jsonl(root / "questions.jsonl")
    expected_metadata = _read_jsonl(root / "expected_metadata.jsonl")
    summary = {
        "status": "baseline_ready",
        "documents": len(documents),
        "questions": len(questions),
        "expected_metadata_rows": len(expected_metadata),
        "live_cloud": False,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
