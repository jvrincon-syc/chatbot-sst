#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app" / "back" / "src"))

from ingestion.config.env import load_secrets_env  # noqa: E402
from ingestion.ocr.doctor import check_ocr_environment  # noqa: E402


def main() -> int:
    load_secrets_env(ROOT / "secrets.env")
    parser = argparse.ArgumentParser(description="Check OCRmyPDF/Tesseract configuration.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = check_ocr_environment()
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"OCR status: {'ok' if report.ok else 'needs configuration'}")
        print(f"OCRmyPDF: {report.ocrmypdf_cmd} ({report.ocrmypdf_version or 'unavailable'})")
        print(f"Tesseract: {report.tesseract_cmd} ({report.tesseract_version or 'unavailable'})")
        print(f"Language: {report.language} ({'available' if report.language_available else 'missing'})")
        print(f"pdfplumber: {'available' if report.pdfplumber_available else 'unavailable'}")
        print(f"PDFium: {'available' if report.pdfium_available else 'unavailable'}")
        print(f"OpenCV: {'available' if report.opencv_available else 'unavailable'}")
        print(f"Ghostscript: {report.ghostscript_version or 'unavailable'}")
        if report.issues:
            print("Issues: " + ", ".join(report.issues))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
