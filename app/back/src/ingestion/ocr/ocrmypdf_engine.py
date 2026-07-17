from __future__ import annotations

import shutil
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ingestion.readers.pdf_digital_reader import PdfPage


class OcrDependencyError(RuntimeError):
    def __init__(self, message: str, reasons: List[str]) -> None:
        super().__init__(message)
        self.reasons = reasons


class OcrMyPdfEngine:
    engine = "tesseract"
    language = "spa"

    def __init__(
        self,
        *,
        ocrmypdf_cmd: Optional[str] = None,
        tesseract_cmd: Optional[str] = None,
        language: Optional[str] = None,
        temp_dir: Optional[Path] = None,
        keep_temporary: bool = False,
        timeout_seconds: Optional[int] = None,
        runner: Callable = subprocess.run,
        text_extractor=None,
    ) -> None:
        self.ocrmypdf_cmd = ocrmypdf_cmd or os.getenv("OCRMYPDF_CMD", "ocrmypdf")
        self.tesseract_cmd = tesseract_cmd or os.getenv("TESSERACT_CMD", "tesseract")
        self.language = language or os.getenv("TESSERACT_LANGUAGE", "spa")
        configured_temp_dir = os.getenv("OCR_TEMP_DIR")
        self.temp_dir = temp_dir or (Path(configured_temp_dir) if configured_temp_dir else None)
        self.keep_temporary = keep_temporary
        self.timeout_seconds = timeout_seconds or int(os.getenv("OCR_TIMEOUT_SECONDS", "180"))
        self.runner = runner
        self.text_extractor = text_extractor
        self.engine_version = "unknown"

    def extract_pages(self, source_path: Path) -> List[Dict]:
        self._validate_tesseract()

        with tempfile.TemporaryDirectory(dir=str(self.temp_dir) if self.temp_dir else None) as temp_name:
            temp_root = Path(temp_name)
            working_input = temp_root / source_path.name
            output_pdf = temp_root / "ocr_output.pdf"
            sidecar_txt = temp_root / "ocr_output.txt"
            shutil.copy2(source_path, working_input)
            command = [
                self.ocrmypdf_cmd,
                "--language",
                self.language,
                "--deskew",
                "--rotate-pages",
                "--force-ocr",
                "--sidecar",
                str(sidecar_txt),
                str(working_input),
                str(output_pdf),
            ]
            try:
                self.runner(command, check=True, capture_output=True, text=True, timeout=self.timeout_seconds)
            except FileNotFoundError as exc:
                raise OcrDependencyError("OCRmyPDF is not installed or not in PATH.", ["ocrmypdf_unavailable"]) from exc
            except subprocess.TimeoutExpired as exc:
                raise OcrDependencyError("OCRmyPDF timed out while processing the document.", ["ocrmypdf_timeout"]) from exc
            except subprocess.CalledProcessError as exc:
                raise OcrDependencyError(
                    "OCRmyPDF failed while processing the document.",
                    ["ocrmypdf_processing_failed"],
                ) from exc

            if self.text_extractor is not None:
                pages = self.text_extractor.extract_pages(output_pdf)
                return [self._page_to_dict(page) for page in pages]
            return self._pages_from_sidecar(sidecar_txt)

    def _validate_tesseract(self) -> None:
        try:
            version = self.runner(
                [self.tesseract_cmd, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            langs = self.runner(
                [self.tesseract_cmd, "--list-langs"],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise OcrDependencyError("Tesseract is not installed or not in PATH.", ["tesseract_unavailable"]) from exc
        except subprocess.CalledProcessError as exc:
            raise OcrDependencyError("Tesseract is not callable.", ["tesseract_unavailable"]) from exc

        self.engine_version = self._parse_tesseract_version(version.stdout)
        languages = {line.strip() for line in langs.stdout.splitlines() if line.strip() and not line.startswith("List ")}
        if self.language not in languages:
            raise OcrDependencyError(
                f"Tesseract language '{self.language}' is not installed.",
                ["tesseract_language_missing"],
            )

    @staticmethod
    def _parse_tesseract_version(output: str) -> str:
        first_line = output.splitlines()[0] if output.splitlines() else ""
        parts = first_line.split()
        return parts[1] if len(parts) > 1 and parts[0].lower().startswith("tesseract") else "unknown"

    @staticmethod
    def _page_to_dict(page) -> Dict:
        if isinstance(page, dict):
            return page
        if isinstance(page, PdfPage):
            return {
                "page_number": page.page_number,
                "text": page.text,
                "confidence": 1.0 if page.text.strip() else 0.0,
                "contains_handwriting": False,
                "deskew_applied": True,
                "rotation_detected_degrees": 0,
            }
        return {
            "page_number": getattr(page, "page_number", 1),
            "text": getattr(page, "text", ""),
            "confidence": 1.0,
            "contains_handwriting": False,
            "deskew_applied": True,
            "rotation_detected_degrees": 0,
        }

    @staticmethod
    def _pages_from_sidecar(sidecar_path: Path) -> List[Dict]:
        text = sidecar_path.read_text(encoding="utf-8") if sidecar_path.exists() else ""
        raw_pages = text.split("\f") if text else [""]
        return [
            {
                "page_number": index,
                "text": page.strip(),
                "confidence": 1.0 if page.strip() else 0.0,
                "contains_handwriting": False,
                "deskew_applied": True,
                "rotation_detected_degrees": 0,
            }
            for index, page in enumerate(raw_pages, start=1)
        ]
