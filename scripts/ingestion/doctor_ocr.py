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
from ingestion.ocr.doctor import check_ocr_environment  # noqa: E402
from core.logging.logger import configure_structured_logging  # noqa: E402


def main() -> int:
    configure_structured_logging(stream=sys.stderr, include_file_handler=False)
    logger = logging.getLogger(__name__)
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Check Tesseract/PDFium OCR configuration.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = check_ocr_environment()
    payload = report.model_dump(mode="json")
    logger.info(
        "ocr_environment_checked",
        extra={
            "stage": "ocr",
            "event": "ocr_environment_checked",
            "status": "completed" if report.ok else "warning",
            "ok": report.ok,
            "issue_count": len(report.issues),
        },
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
