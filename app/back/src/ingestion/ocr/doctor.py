from __future__ import annotations

import os
import importlib.util
import subprocess
from typing import Callable, List, Optional

from pydantic import BaseModel, Field


class OcrDoctorReport(BaseModel):
    ok: bool
    ocrmypdf_enabled: bool
    ocrmypdf_cmd: str
    tesseract_cmd: str
    language: str
    ocrmypdf_available: bool
    tesseract_available: bool
    language_available: bool
    pdfplumber_available: bool
    pdfium_available: bool
    opencv_available: bool
    ghostscript_available: bool
    ocrmypdf_version: Optional[str] = None
    tesseract_version: Optional[str] = None
    ghostscript_version: Optional[str] = None
    available_languages: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


def check_ocr_environment(
    *,
    ocrmypdf_cmd: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
    ghostscript_cmd: Optional[str] = None,
    language: Optional[str] = None,
    runner: Callable = subprocess.run,
    module_available: Callable[[str], bool] | None = None,
) -> OcrDoctorReport:
    ocrmypdf_enabled = _env_flag("OCR_ENABLE_OCRMYPDF", default=False)
    resolved_ocrmypdf = ocrmypdf_cmd or _env_value("OCRMYPDF_CMD", "ocrmypdf")
    resolved_tesseract = tesseract_cmd or os.getenv("TESSERACT_CMD", "tesseract")
    resolved_ghostscript = ghostscript_cmd or _env_value("GHOSTSCRIPT_CMD", "gs")
    resolved_language = language or os.getenv("TESSERACT_LANGUAGE", "spa")
    module_available = module_available or _module_available
    issues: List[str] = []

    ocrmypdf_available = False
    ocrmypdf_version = None
    try:
        result = runner([resolved_ocrmypdf, "--version"], check=True, capture_output=True, text=True)
        ocrmypdf_available = True
        version_output = (result.stdout or result.stderr or "").strip()
        ocrmypdf_version = version_output.splitlines()[0] if version_output else "unknown"
    except (FileNotFoundError, subprocess.CalledProcessError):
        if ocrmypdf_enabled:
            issues.append("ocrmypdf_unavailable")

    tesseract_available = False
    tesseract_version = None
    available_languages: List[str] = []
    try:
        version = runner([resolved_tesseract, "--version"], check=True, capture_output=True, text=True)
        tesseract_available = True
        tesseract_version = _parse_tesseract_version(version.stdout)
        langs = runner([resolved_tesseract, "--list-langs"], check=True, capture_output=True, text=True)
        available_languages = _parse_languages(langs.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError):
        issues.append("tesseract_unavailable")

    language_available = resolved_language in set(available_languages)
    if tesseract_available and not language_available:
        issues.append("tesseract_language_missing")

    pdfplumber_available = module_available("pdfplumber")
    if not pdfplumber_available:
        issues.append("pdfplumber_unavailable")
    pdfium_available = module_available("pypdfium2")
    if not pdfium_available:
        issues.append("pdfium_unavailable")
    opencv_available = module_available("cv2")
    if not opencv_available:
        issues.append("opencv_unavailable")

    ghostscript_available = False
    ghostscript_version = None
    try:
        gs = runner([resolved_ghostscript, "--version"], check=True, capture_output=True, text=True)
        ghostscript_available = True
        ghostscript_version = (gs.stdout or gs.stderr or "").strip().splitlines()[0] or "unknown"
    except (FileNotFoundError, subprocess.CalledProcessError):
        if ocrmypdf_enabled:
            issues.append("ghostscript_unavailable")

    return OcrDoctorReport(
        ok=not issues,
        ocrmypdf_enabled=ocrmypdf_enabled,
        ocrmypdf_cmd=resolved_ocrmypdf,
        tesseract_cmd=resolved_tesseract,
        language=resolved_language,
        ocrmypdf_available=ocrmypdf_available,
        tesseract_available=tesseract_available,
        language_available=language_available,
        pdfplumber_available=pdfplumber_available,
        pdfium_available=pdfium_available,
        opencv_available=opencv_available,
        ghostscript_available=ghostscript_available,
        ocrmypdf_version=ocrmypdf_version,
        tesseract_version=tesseract_version,
        ghostscript_version=ghostscript_version,
        available_languages=available_languages,
        issues=issues,
    )


def _parse_tesseract_version(output: str) -> str:
    first_line = output.splitlines()[0] if output.splitlines() else ""
    parts = first_line.split()
    return parts[1] if len(parts) > 1 and parts[0].lower().startswith("tesseract") else "unknown"


def _parse_languages(output: str) -> List[str]:
    languages = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("List "):
            continue
        languages.append(stripped)
    return languages


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped or default
